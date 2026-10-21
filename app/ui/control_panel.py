"""
Ana kontrol paneli: dil seçimi, bölge seçimi, başlat/durdur, görünüm ayarları.
"""
from __future__ import annotations

import importlib.util

from PySide6.QtCore import QObject, QRect, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QDialog, QMessageBox, QProgressBar, QSlider, QSpinBox,
    QVBoxLayout, QWidget, QScrollArea, QSizePolicy,
)
from .menu_widgets import (MenuCheckBox as QCheckBox, MenuComboBox as QComboBox,
                          MenuFormLayout as QFormLayout, MenuGroupBox as QGroupBox,
                          MenuLabel as QLabel, MenuButton as QPushButton, menu_text)
from .usage_monitor import UsageMonitor

from ..config import APP_ICON, PROJECT_ROOT, LANGS, PRESET_NAMES, TRANSLATION_MODELS, Settings
from ..core.pipeline import TranslationWorker
from ..platform_utils import exclude_from_capture, logical_to_capture_rect
from .overlay import OverlayWindow
from .region_selector import RegionSelector

HOTKEYS_TEXT = (
    "Kısayollar:  Ctrl+Alt+T başlat/durdur  •  Ctrl+Alt+R bölge seç\n"
    "Ctrl+Alt+H çeviriyi gizle/göster (orijinali gör)  •  Ctrl+Alt+Y şimdi çevir"
)


class HotkeyBridge(QObject):
    toggle_run = Signal()
    select_region = Signal()
    toggle_overlay = Signal()
    translate_now = Signal()


def start_global_hotkeys(bridge: HotkeyBridge):
    try:
        from pynput import keyboard
    except Exception:
        print("[kısayol] pynput yok, global kısayollar devre dışı.")
        return None
    try:
        hk = keyboard.GlobalHotKeys({
            "<ctrl>+<alt>+t": bridge.toggle_run.emit,
            "<ctrl>+<alt>+r": bridge.select_region.emit,
            "<ctrl>+<alt>+h": bridge.toggle_overlay.emit,
            "<ctrl>+<alt>+y": bridge.translate_now.emit,
        })
        hk.daemon = True
        hk.start()
        return hk
    except Exception as e:
        print(f"[kısayol] başlatılamadı: {e}")
        return None


class ControlPanel(QWidget):
    def __init__(self, enable_hotkeys=True) -> None:
        super().__init__()
        self.s = Settings.load()
        self.setWindowTitle("mergen")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(370)
        self.setObjectName("controlPanel")
        self.setMaximumWidth(420)

        self.worker: TranslationWorker | None = None
        self.thread: QThread | None = None
        self.running = False
        self.region: QRect | None = None
        self._selector: RegionSelector | None = None
        self._start_after_select = False

        # Overlay: başlangıçta birincil ekranı kaplar (boş ve tıklama geçirgen)
        self.overlay = OverlayWindow(self.s)
        self.overlay.setGeometry(QGuiApplication.primaryScreen().geometry())
        self.overlay.show()
        self.overlay.ensure_platform_setup()
        self.overlay.setVisible(self.s.overlay_visible)

        self._build_ui()
        self.usage_monitor = UsageMonitor(self)
        self.usage_monitor.readings.connect(self._update_usage)
        self._apply_usage_visibility()

        if self.s.last_region and len(self.s.last_region) == 4:
            self._apply_region(QRect(*self.s.last_region))

        self.bridge = HotkeyBridge()
        self.bridge.toggle_run.connect(self.toggle_run)
        self.bridge.select_region.connect(lambda: self.select_region(False))
        self.bridge.toggle_overlay.connect(self.toggle_overlay_visible)
        self.bridge.translate_now.connect(self.translate_now)
        self.hotkeys = start_global_hotkeys(self.bridge) if enable_hotkeys else None


    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(14)

        g_src = QGroupBox("çeviri")
        f_src = QFormLayout(g_src)
        f_src.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        f_src.setVerticalSpacing(10)
        self.cb_lang = QComboBox()
        for code, info in LANGS.items():
            self.cb_lang.addItem(info["name"], code)
        self.cb_lang.setCurrentIndex(max(0, self.cb_lang.findData(self.s.source_lang)))
        self.cb_lang.currentIndexChanged.connect(self._on_lang_changed)
        f_src.addRow("Kaynak dil", self.cb_lang)
        self.cb_ocr = QComboBox()
        self.cb_ocr.currentIndexChanged.connect(self._on_ocr_changed)
        f_src.addRow("OCR motoru", self.cb_ocr)
        self._refresh_ocr_menu()

        root.addWidget(g_src)
        row = QHBoxLayout()
        self.btn_region = QPushButton("Bölge seç")
        self.btn_region.clicked.connect(lambda: self.select_region(False))
        self.btn_full = QPushButton("Tüm ekran")
        self.btn_full.clicked.connect(self._select_fullscreen)
        row.addWidget(self.btn_region)
        row.addWidget(self.btn_full)
        root.addLayout(row)
        self.lbl_region = QLabel("Henüz seçilmedi", self)
        self.lbl_region.hide()  # Region details remain available to existing code, without a visible card.

        self.btn_run = QPushButton("▶  Başlat")
        self.btn_run.setObjectName('run')
        self.btn_run.setMinimumHeight(42)
        f = self.btn_run.font()
        f.setBold(True)
        self.btn_run.setFont(f)
        self.btn_run.clicked.connect(self.toggle_run)
        self.btn_now = QPushButton("Şimdi çevir")
        self.btn_now.setFixedHeight(36)
        self.btn_now.clicked.connect(self.translate_now)

        action_row = QHBoxLayout()
        self.btn_overlay = QPushButton("çeviriyi gizle" if self.s.overlay_visible else "çeviriyi göster")
        self.btn_overlay.setFixedHeight(36)
        self.btn_overlay.clicked.connect(self.toggle_overlay_visible)
        self.btn_settings = QPushButton("")
        self.btn_settings.setObjectName('settings')
        self.btn_settings.setIcon(QIcon(str(PROJECT_ROOT / 'assets' / 'ui' / 'settings.svg')))
        self.btn_settings.setFixedHeight(36)
        self.btn_settings.setToolTip('ayarlar')
        self.btn_settings.setAccessibleName('ayarlar')
        self.btn_settings.clicked.connect(self._show_settings)
        action_row.addWidget(self.btn_now, 1)
        action_row.addWidget(self.btn_overlay, 1)
        action_row.addWidget(self.btn_settings, 1)
        dock = QWidget()
        dock.setObjectName("toolDock")
        dock.setLayout(action_row)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        for button in (self.btn_now, self.btn_overlay, self.btn_settings):
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        root.addWidget(dock)
        root.addWidget(self.btn_run)

        self.lbl_status = QLabel("Hazır")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setObjectName("status")
        root.addWidget(self.lbl_status)
        root.addStretch(1)

        self.usage_group = QGroupBox("sistem kullanımı")
        self.usage_group.setObjectName("usageGroup")
        usage_l = QVBoxLayout(self.usage_group)
        usage_l.setSpacing(14)
        self.usage_rows = {}
        self.usage_values = {}
        for key, label in (('gpu', 'gpu'), ('vram', 'vram'), ('cpu', 'cpu')):
            container = QWidget()
            container.setObjectName("usageRow")
            stack = QVBoxLayout(container)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(5)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            name = QLabel(label)
            name.setFixedWidth(36)
            name.setObjectName("usageName")
            row.addWidget(name)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(5)
            value_label = QLabel('bekleniyor')
            value_label.setObjectName('usageValue')
            value_label.setFixedWidth(92)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.usage_values[key] = value_label
            bar.setToolTip('tüm sistem kullanımı' if key != 'vram' else 'kullanılan ekran kartı belleği / toplam bellek')
            row.addStretch(1)
            row.addWidget(value_label)
            stack.addLayout(row)
            stack.addWidget(bar)
            container.setMinimumHeight(28)
            setattr(self, key + '_bar', bar)
            self.usage_rows[key] = container
            usage_l.addWidget(container)
        root.addWidget(self.usage_group)

        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("mergen · ayarlar")
        self.settings_dialog.setMinimumWidth(370)
        dialog_root = QVBoxLayout(self.settings_dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        settings_content = QWidget()
        settings_root = QVBoxLayout(settings_content)
        settings_root.setContentsMargins(2, 2, 2, 2)
        settings_root.setSpacing(8)
        scroll.setWidget(settings_content)
        dialog_root.addWidget(scroll)
        self.settings_dialog.resize(410, min(620, QGuiApplication.primaryScreen().availableGeometry().height() - 80))
        g_view = QGroupBox("Görünüm")
        f_view = QFormLayout(g_view)
        f_view.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        f_view.setVerticalSpacing(6)
        self.chk_visible = QCheckBox("Çeviriyi göster")
        self.chk_visible.setChecked(self.s.overlay_visible)
        self.chk_visible.toggled.connect(self._on_visible_changed)

        self.cb_panel_theme = QComboBox()
        for code, name in (("green", "Yeşil"), ("white", "Beyaz"),
                           ("navy", "Lacivert"), ("black", "Siyah"), ("sepia", "Sepya")):
            self.cb_panel_theme.addItem(name, code)
        self.cb_panel_theme.setCurrentIndex(max(0, self.cb_panel_theme.findData(self.s.panel_theme)))
        self.cb_panel_theme.currentIndexChanged.connect(self._on_panel_theme_changed)
        f_view.addRow("Panel teması:", self.cb_panel_theme)

        self.cb_theme = QComboBox()
        for code, name in (("white", "Beyaz"), ("black", "Siyah"), ("sepia", "Sepya"),
                           ("navy", "Lacivert"), ("gray", "Gri")):
            self.cb_theme.addItem(name, code)
        self.cb_theme.setCurrentIndex(max(0, self.cb_theme.findData(self.s.theme)))
        self.cb_theme.currentIndexChanged.connect(self._on_theme_changed)
        f_view.addRow("Çeviri kutusu teması:", self.cb_theme)

        self.sl_opacity = QSlider(Qt.Orientation.Horizontal)
        self.sl_opacity.setRange(30, 100)
        self.sl_opacity.setValue(int(self.s.overlay_opacity * 100))
        self.sl_opacity.valueChanged.connect(self._on_opacity)
        f_view.addRow("Kutu opaklığı:", self.sl_opacity)

        self.cb_font = QComboBox()
        for family in QFontDatabase.families():
            self.cb_font.addItem(family, family)
        if self.cb_font.findData(self.s.font_family) < 0:
            self.cb_font.addItem(self.s.font_family, self.s.font_family)
        self.cb_font.setCurrentIndex(self.cb_font.findData(self.s.font_family))
        self.cb_font.currentIndexChanged.connect(lambda _: self._on_font(QFont(self.cb_font.currentData())))
        f_view.addRow("Yazı tipi:", self.cb_font)

        self.sp_maxfont = QSpinBox()
        self.sp_maxfont.setRange(10, 96)
        self.sp_maxfont.setValue(self.s.max_font_px)
        self.sp_maxfont.valueChanged.connect(self._on_maxfont)
        f_view.addRow("Maks. yazı boyu (px):", self.sp_maxfont)

        self.chk_bold = QCheckBox("Kalın yazı")
        self.chk_bold.setChecked(self.s.font_bold)
        self.chk_bold.toggled.connect(self._on_bold)
        settings_root.addWidget(g_view)

        g_perf = QGroupBox("Performans")
        f_perf = QFormLayout(g_perf)
        f_perf.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        f_perf.setVerticalSpacing(6)
        self.cb_preset = QComboBox()
        for key, name in PRESET_NAMES.items():
            self.cb_preset.addItem(name, key)
        self.cb_preset.setCurrentIndex(max(0, self.cb_preset.findData(self.s.speed_preset)))
        self.cb_preset.currentIndexChanged.connect(self._on_preset)
        f_perf.addRow("Hız modu:", self.cb_preset)

        # Bunu onay kutusu yerine açık bir model seçimi olarak tutuyoruz.
        # Böylece kullanıcının hangi PaddleOCR sürümünün seçili olduğu net olur.
        self.cb_paddle_model = QComboBox()
        self.cb_paddle_model.addItem("Mobil — hızlı (önerilen)", True)
        self.cb_paddle_model.addItem("Sunucu — daha doğru, daha yavaş", False)
        self.cb_paddle_model.setCurrentIndex(
            max(0, self.cb_paddle_model.findData(self.s.paddle_mobile))
        )
        self.cb_paddle_model.currentIndexChanged.connect(self._on_paddle_speed_changed)
        self.lbl_paddle_model = QLabel("PaddleOCR sürümü:")
        f_perf.addRow(self.lbl_paddle_model, self.cb_paddle_model)

        self.sp_settle = QSpinBox()
        self.sp_settle.setRange(0, 2000)
        self.sp_settle.setSingleStep(50)
        self.sp_settle.setSuffix(" ms")
        self.sp_settle.setValue(self.s.settle_ms)
        self.sp_settle.valueChanged.connect(lambda v: setattr(self.s, "settle_ms", v))
        f_perf.addRow("Kaydırma durunca bekle:", self.sp_settle)

        self.chk_scroll = QCheckBox("kaydırmayı takip et")
        self.chk_scroll.setChecked(self.s.scroll_tracking)
        self.chk_scroll.toggled.connect(lambda v: setattr(self.s, "scroll_tracking", v))

        self.chk_manga = QCheckBox("japonca için manga-ocr kullan")
        self.chk_manga.setChecked(self.s.use_manga_ocr)
        self.chk_manga.toggled.connect(self._on_manga_enabled)
        self.cb_manga_device = QComboBox()
        self.cb_manga_device.addItem('Otomatik — izole GPU / CPU', 'auto')
        self.cb_manga_device.addItem('GPU — izole CUDA', 'cuda')
        self.cb_manga_device.addItem('CPU — düşük VRAM', 'cpu')
        self.cb_manga_device.setCurrentIndex(max(0, self.cb_manga_device.findData(self.s.manga_device)))
        self.cb_manga_device.currentIndexChanged.connect(self._on_manga_device_changed)
        self.lbl_manga_device = QLabel('manga-ocr cihazı:')
        f_perf.addRow(self.lbl_manga_device, self.cb_manga_device)
        self.chk_bubbles = QCheckBox("Konuşma balonlarını ayır")
        self.chk_bubbles.setChecked(self.s.bubble_detection)
        self.chk_bubbles.toggled.connect(lambda v: setattr(self.s, "bubble_detection", v))
        self.cb_model = QComboBox()
        for folder, name in TRANSLATION_MODELS.items():
            if (self.s.model_path.parent / folder / "model.bin").exists():
                self.cb_model.addItem(name, folder)
        current = self.cb_model.findData(self.s.translation_model)
        if current >= 0:
            self.cb_model.setCurrentIndex(current)
        self.cb_model.currentIndexChanged.connect(self._on_model_changed)
        f_perf.addRow("Çeviri modeli:", self.cb_model)
        self.cb_chinese_translation = QComboBox()
        self.cb_chinese_translation.addItem("İngilizce üzerinden — daha yavaş", True)
        self.cb_chinese_translation.addItem("Doğrudan + şüpheli terim kontrolü", False)
        self.cb_chinese_translation.setCurrentIndex(
            max(0, self.cb_chinese_translation.findData(self.s.chinese_translation_via_english))
        )
        self.cb_chinese_translation.setToolTip(
            "Doğrudan modda yalnızca şüpheli terim bulunan balon yeniden çevrilir. "
            "İngilizce üzerinden seçeneği tüm Çince balonları iki aşamada çevirir ve daha yavaştır. "
            "İki seçenek de yereldir. [?] işareti, terim kontrolünün sonuçtan emin olamadığını gösterir."
        )
        self.cb_chinese_translation.currentIndexChanged.connect(self._on_chinese_translation_changed)
        f_perf.addRow("Çince çeviri:", self.cb_chinese_translation)
        self.btn_clear_context = QPushButton('konuşma hafızasını temizle')
        self.btn_clear_context.setToolTip('yeni bölüm veya hikâye için oturumluk isimleri ve son konuşmaları temizler; modeli yeniden yüklemez')
        self.btn_clear_context.clicked.connect(self._clear_context)
        f_perf.addRow(self.btn_clear_context)
        model_note = QLabel("Kaliteli model için kurulumda ‘Kaliteli’ seçeneğini seçin.\nNLLB yalnızca ticari olmayan kullanım içindir.")
        model_note.setWordWrap(True)
        f_perf.addRow(model_note)
        self.lbl_devices = QLabel("Cihaz: (başlatınca görünür)")
        self.lbl_devices.setWordWrap(True)
        self.lbl_devices.setStyleSheet("font-weight: bold;")
        f_perf.addRow(self.lbl_devices)
        settings_root.addWidget(g_perf)

        options = QGroupBox('seçenekler')
        options_layout = QVBoxLayout(options)
        for checkbox in (self.chk_visible, self.chk_bold, self.chk_scroll, self.chk_manga, self.chk_bubbles):
            options_layout.addWidget(checkbox)
        self.chk_context = QCheckBox('oturumluk isim ve terim tutarlılığı')
        self.chk_context.setChecked(self.s.session_context)
        self.chk_context.setToolTip('son 24 farklı konuşmayı ve doğrulanmış isimleri yalnızca ram içinde tutar; önceki konuşmaları nllb girdisine eklemez')
        self.chk_context.toggled.connect(self._on_context_changed)
        options_layout.addWidget(self.chk_context)
        self.chk_usage = QCheckBox('sistem kullanımını göster')
        self.chk_usage.setChecked(self.s.show_system_usage)
        self.chk_usage.toggled.connect(lambda checked: self._on_usage_option('show_system_usage', checked))
        options_layout.addWidget(self.chk_usage)
        self.usage_checks = {}
        for key, label in (('gpu', 'gpu kullanım yüzdesi'), ('vram', 'vram kullanım yüzdesi'), ('cpu', 'cpu kullanım yüzdesi')):
            checkbox = QCheckBox(label)
            checkbox.setChecked(getattr(self.s, 'show_' + key + '_usage'))
            checkbox.toggled.connect(lambda checked, k=key: self._on_usage_option('show_' + k + '_usage', checked))
            self.usage_checks[key] = checkbox
            options_layout.addWidget(checkbox)
        settings_root.addWidget(options)

        hk = QLabel(HOTKEYS_TEXT)
        hk.setStyleSheet("color: gray; font-size: 11px;")
        hk.setWordWrap(True)
        settings_root.addWidget(hk)
        close = QPushButton("Kapat")
        close.clicked.connect(self.settings_dialog.close)
        dialog_root.addWidget(close)

        self._update_paddle_model_visibility()
        self._apply_theme()

    def _show_settings(self) -> None:
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _clear_context(self) -> None:
        if self.worker is not None:
            self.worker.reset_translation_context()
        self._set_status('konuşma hafızası temizlendi')

    def _on_context_changed(self, enabled: bool) -> None:
        self.s.session_context = enabled
        if self.worker is not None:
            self.worker.reset_translation_context(enabled)

    def _apply_theme(self) -> None:
        # Glass-inspired gradients are rendered by Qt on all supported Windows versions.
        # Panel styling is independent of the text overlay's theme and opacity.
        palettes = {
            # background, text, surface, border, primary, muted, primary text, complementary control
            "green": ("#242722", "#f3f5ed", "#30352d", "#535c4b", "#d8ed9b", "#bcc5b2", "#25321a", "#dcb2eb"),
            "white": ("#f0f2ec", "#293024", "#e4e8de", "#b9c2b0", "#cee799", "#5c6653", "#25321a", "#674484"),
            "navy": ("#171e2c", "#edf2fc", "#232e41", "#475770", "#a9caff", "#b5c2d8", "#152339", "#f0bc85"),
            "black": ("#191a1c", "#f3f3f5", "#28292d", "#51525b", "#dedee5", "#bcbcc7", "#202127", "#ededf2"),
            "sepia": ("#efe5d5", "#423323", "#e4d7c1", "#b7a58b", "#73532d", "#6e5d46", "#fff6e8", "#385d8a"),
        }
        bg, fg, surface, border, accent, muted, ink, contrast = palettes.get(self.s.panel_theme, palettes["green"])
        light = self.s.panel_theme in ("white", "sepia")
        shine = "rgba(255,255,255,150)" if light else "rgba(255,255,255,30)"
        check = PROJECT_ROOT / "assets" / "ui" / ("check-light.svg" if light else "check-dark.svg")
        rail = "rgba(0,0,0,22)" if light else "rgba(255,255,255,28)"
        glass = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {shine},stop:1 {surface})"
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {fg}; font-family: 'Segoe UI'; font-size: 12px; }}
            QLabel {{ background: transparent; }}
            QGroupBox {{ background: {surface}; border: 1px solid {border}; border-radius: 17px;
                margin-top: 12px; padding: 14px 10px 10px; font-weight: 500; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 5px; color: {muted}; }}
            QPushButton, QComboBox, QSpinBox {{ background: {glass}; border: 1px solid {border};
                border-radius: 12px; padding: 10px; min-height: 18px; }}
            QPushButton:hover, QComboBox:hover {{ border-color: {accent}; }}
            QPushButton:pressed {{ background: {surface}; }}
            QPushButton:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {accent}; }}
            QPushButton:disabled {{ color: {muted}; }}
            QComboBox::drop-down {{ border: 0; width: 20px; }}
            QComboBox {{ padding-right: 22px; }}
            QComboBox QAbstractItemView {{ background: {bg}; color: {fg}; selection-background-color: {accent}; selection-color: {ink}; }}
            QWidget#toolDock {{ background: transparent; border: 0; }}
            QWidget#toolDock QPushButton {{ background: {glass}; border: 1px solid {border}; border-radius: 17px; padding: 5px; min-height: 24px; }}
            QWidget#toolDock QPushButton:hover {{ background: {surface}; }}
            QPushButton#run {{ background: {accent}; color: {ink}; border: 0; border-radius: 15px; font-weight: 600; }}
            QPushButton#run:hover {{ border: 2px solid {fg}; }}
            QPushButton#settings {{ padding: 5px; }}
            QCheckBox {{ spacing: 8px; padding: 5px 0; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {border}; border-radius: 5px; background: {bg}; }}
            QCheckBox::indicator:checked {{ background: {contrast}; border: 1px solid {contrast}; image: url("{check.as_posix()}"); }}
            QSlider::groove:horizontal {{ background: {border}; height: 5px; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {contrast}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {contrast}; border: 2px solid {fg}; width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }}
            QProgressBar {{ border: 0; background: {rail}; border-radius: 2px; min-height: 5px; max-height: 5px; }}
            QProgressBar::chunk {{ background: {contrast}; border-radius: 2px; }}
            QWidget#toolDock QPushButton:focus {{ border: 2px solid {contrast}; }}
            QWidget#usageRow {{ background: transparent; border: 0; }}
            QLabel#usageName {{ color: {muted}; background: transparent; font-size: 11px; }}
            QLabel#usageValue {{ color: {fg}; background: transparent; font-size: 12px; font-weight: 600; }}
            QDialog QGroupBox {{ padding: 8px 8px 6px; border-radius: 14px; }}
            QDialog QPushButton, QDialog QComboBox, QDialog QSpinBox {{ padding: 5px 8px; border-radius: 9px; min-height: 17px; }}
            QDialog QCheckBox {{ padding: 2px 0; }}
            QLabel#status {{ color: {muted}; padding: 4px; }}
            QScrollArea {{ border: 0; }}
        """)

    def _on_panel_theme_changed(self, _idx: int) -> None:
        self.s.panel_theme = self.cb_panel_theme.currentData()
        self._apply_theme()

    def _on_theme_changed(self, _idx: int) -> None:
        self.s.theme = self.cb_theme.currentData()
        self.overlay.refresh_style()

    def _on_model_changed(self, _idx: int) -> None:
        folder = self.cb_model.currentData()
        if not folder or folder == self.s.translation_model:
            return
        self.s.translation_model = folder
        self._set_status("Çeviri modeli değişti. Etkinleşmesi için uygulamayı yeniden başlatın.")

    def _on_usage_option(self, name: str, checked: bool) -> None:
        setattr(self.s, name, checked)
        self._apply_usage_visibility()
        self.s.save()

    def _apply_usage_visibility(self) -> None:
        enabled = []
        for key in ('gpu', 'vram', 'cpu'):
            show = self.s.show_system_usage and getattr(self.s, 'show_' + key + '_usage')
            self.usage_rows[key].setVisible(show)
            self.usage_checks[key].setEnabled(self.s.show_system_usage)
            enabled.append(show)
        self.usage_group.setVisible(any(enabled))
        if hasattr(self, 'usage_monitor'):
            self.usage_monitor.set_enabled(*enabled)
        # Reclaim hidden rows so the compact panel doesn't retain empty space.
        self.layout().activate()
        self.resize(self.width(), self.sizeHint().height())

    def _update_usage(self, values: dict) -> None:
        for key, value in values.items():
            bar = getattr(self, key + '_bar')
            bar.setValue(value if value is not None else 0)
            self.usage_values[key].setText(f'{value}%' if value is not None else 'kullanılamıyor')
            source = self.usage_monitor.source if key in ('gpu', 'vram') else 'tüm sistem'
            detail = 'en yoğun gpu motoru' if key == 'gpu' and source.startswith('windows') else key
            bar.setToolTip(f'{detail}: {value}% · {source}' if value is not None else f'{key}: ölçüm kullanılamıyor')

    # ------------------------------------------------------------------ worker
    def _ensure_worker(self) -> None:
        if self.worker is not None:
            return
        self.thread = QThread(self)
        self.worker = TranslationWorker(self.s, self.overlay.is_capture_excluded())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self._set_status)
        self.worker.devices.connect(self.lbl_devices.setText)
        self.worker.error.connect(self._on_worker_error)
        self.worker.blocks_ready.connect(self.overlay.set_blocks)
        self.worker.clear_requested.connect(self.overlay.clear_blocks)
        self.worker.hide_request.connect(self._on_hide_request)
        self.thread.start()
        if self.region is not None:
            self._push_region()

    def _push_region(self) -> None:
        if self.worker is None or self.region is None:
            return
        cap = logical_to_capture_rect(self.region)
        self.worker.set_region(cap, (self.region.width(), self.region.height()))

    def _on_hide_request(self, hidden: bool) -> None:
        # Paylaşılabilir katmanı kendi OCR görüntümüzden geçici olarak çıkar.
        if hidden:
            self.overlay.hide()
            QGuiApplication.processEvents()
            if self.worker:
                self.worker.ack_hidden()
        elif self.s.overlay_visible:
            self.overlay.show()

    def _on_worker_error(self, msg: str) -> None:
        self._set_status(f"HATA: {msg}")
        QMessageBox.critical(self, "hata", menu_text(msg))
        self.running = False
        self.btn_run.setText("▶  Başlat")
        if self.thread:
            self.thread.quit()
            self.thread.wait(2000)
        self.worker = None
        self.thread = None

    # ------------------------------------------------------------------ eylemler
    def toggle_run(self) -> None:
        if self.region is None:
            self.select_region(start_after=True)
            return
        self._ensure_worker()
        self.running = not self.running
        self.worker.set_active(self.running)
        self.btn_run.setText("■  Durdur" if self.running else "▶  Başlat")
        if not self.running:
            self.overlay.clear_blocks()
            self._set_status("Durduruldu.")
        else:
            self._set_status("Çalışıyor…")

    def translate_now(self) -> None:
        if self.region is None:
            self.select_region(start_after=False)
            return
        self._ensure_worker()
        self.worker.force_once()

    def toggle_overlay_visible(self) -> None:
        self.chk_visible.setChecked(not self.chk_visible.isChecked())

    def select_region(self, start_after: bool = False) -> None:
        if self._selector is not None:
            return
        self._start_after_select = start_after
        self.overlay.clear_blocks()
        self._selector = RegionSelector()
        self._selector.region_selected.connect(self._on_region_selected)
        self._selector.cancelled.connect(self._on_region_cancelled)
        self._selector.start()

    def _select_fullscreen(self) -> None:
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        self._apply_region(screen.geometry())

    def _on_region_selected(self, rect: QRect) -> None:
        self._selector = None
        self._apply_region(rect)
        if self._start_after_select and not self.running:
            self.toggle_run()

    def _on_region_cancelled(self) -> None:
        self._selector = None

    def _apply_region(self, rect: QRect) -> None:
        self.region = QRect(rect)
        self.s.last_region = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.overlay.set_region(rect)
        if self.s.overlay_visible:
            self.overlay.show()
        self.overlay.flash_border(True)
        QTimer.singleShot(900, lambda: self.overlay.flash_border(False))
        self.lbl_region.setText(f"{rect.x()},{rect.y()}  {rect.width()}×{rect.height()}")
        self._push_region()

    # ------------------------------------------------------------------ ayar olayları
    def _on_lang_changed(self, _idx: int) -> None:
        code = self.cb_lang.currentData()
        self.s.source_lang = code
        if code == "ja" and not self.s.use_manga_ocr:
            # Dikey Japonca için genel OCR yerine manga-ocr gerekir.
            self.s.use_manga_ocr = True
            self.chk_manga.blockSignals(True)
            self.chk_manga.setChecked(True)
            self.chk_manga.blockSignals(False)
        self._refresh_ocr_menu()
        self._update_paddle_model_visibility()
        self.overlay.clear_blocks()
        if self.worker:
            self.worker.set_language(code)

    def _refresh_ocr_menu(self) -> None:
        """Yüklü durumunu sade biçimde doğrudan motor menüsünde göster."""
        selected = self.cb_ocr.currentData() or self.s.ocr_engine
        installed = {
            "manga_ocr": (importlib.util.find_spec("manga_ocr") is not None
                          or (PROJECT_ROOT / '.manga-venv' / 'Scripts' / 'python.exe').is_file()),
            "paddleocr": (importlib.util.find_spec("paddleocr") is not None
                          and importlib.util.find_spec("paddle") is not None),
        }
        mark = lambda key: "Yüklü" if installed[key] else "Eksik"
        options = (
            ("Otomatik (önerilen)", "auto"),
            (f"manga-ocr — Japonca için önerilen ({mark('manga_ocr')})", "manga_ocr"),
            (f"PaddleOCR — hızlı ({mark('paddleocr')})", "paddleocr"),
        )
        self.cb_ocr.blockSignals(True)
        self.cb_ocr.clear()
        for text, key in options:
            self.cb_ocr.addItem(text, key)
        self.cb_ocr.setCurrentIndex(max(0, self.cb_ocr.findData(selected)))
        self.cb_ocr.blockSignals(False)

    def _on_ocr_changed(self, _idx: int) -> None:
        engine = self.cb_ocr.currentData()
        self.s.ocr_engine = engine
        self._update_paddle_model_visibility()
        self.overlay.clear_blocks()
        if self.worker:
            self.worker.set_ocr_engine(engine)
            # OCR motoru değiştiğinde, ekranda aynı sayfa dursa bile yeni motoru tara.
            self.worker.force_once()
        self._set_status("OCR motoru değişti; yeni motor yükleniyor…")

    def _update_paddle_model_visibility(self) -> None:
        """Mobil/sunucu seçimi yalnızca PaddleOCR elle seçildiğinde anlamlıdır."""
        show = self.cb_ocr.currentData() == "paddleocr"
        self.lbl_paddle_model.setVisible(show)
        self.cb_paddle_model.setVisible(show)
        show_manga = self.s.source_lang == 'ja' and self.cb_ocr.currentData() in ('auto', 'manga_ocr')
        self.lbl_manga_device.setVisible(show_manga)
        self.cb_manga_device.setVisible(show_manga)

    def _on_manga_device_changed(self, _idx: int) -> None:
        self.s.manga_device = self.cb_manga_device.currentData()
        if self.worker and self.s.source_lang == 'ja':
            self.worker.set_ocr_engine(self.s.ocr_engine)
            self.worker.force_once()
        self._set_status('manga-ocr cihazı değişti; izole yardımcı işlem yeniden yüklenecek.')

    def _on_manga_enabled(self, enabled: bool) -> None:
        self.s.use_manga_ocr = enabled
        if self.worker and self.s.source_lang == 'ja' and self.s.ocr_engine == 'auto':
            self.worker.set_ocr_engine(self.s.ocr_engine)
            self.worker.force_once()

    def _on_paddle_speed_changed(self, _idx: int) -> None:
        self.s.paddle_mobile = bool(self.cb_paddle_model.currentData())
        if self.worker and self.s.ocr_engine in ("auto", "paddleocr"):
            self.worker.set_ocr_engine(self.s.ocr_engine)
            self.worker.force_once()
        self._set_status("PaddleOCR hızı değişti; sonraki taramada yeni model kullanılacak.")

    def _on_chinese_translation_changed(self, _idx: int) -> None:
        self.s.chinese_translation_via_english = bool(self.cb_chinese_translation.currentData())
        if self.worker:
            self.worker.force_once()
        self._set_status("Çince çeviri yolu değişti; sonraki taramada uygulanacak.")

    def _on_preset(self, _idx: int) -> None:
        self.s.apply_preset(self.cb_preset.currentData())
        self.sp_settle.blockSignals(True)
        self.sp_settle.setValue(self.s.settle_ms)
        self.sp_settle.blockSignals(False)

    def _on_visible_changed(self, v: bool) -> None:
        self.s.overlay_visible = v
        self.overlay.setVisible(v)
        self.btn_overlay.setText("Çeviriyi gizle" if v else "Çeviriyi göster")

    def _on_opacity(self, v: int) -> None:
        self.s.overlay_opacity = v / 100
        self.overlay.refresh_style()

    def _on_font(self, f: QFont) -> None:
        self.s.font_family = f.family()
        self.overlay.refresh_style()

    def _on_maxfont(self, v: int) -> None:
        self.s.max_font_px = v
        self.overlay.refresh_style()

    def _on_bold(self, v: bool) -> None:
        self.s.font_bold = v
        self.overlay.refresh_style()

    def _set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    # ------------------------------------------------------------------ kapanış
    def closeEvent(self, e) -> None:
        self.usage_monitor.close()
        # Model initialization/inference may outlast the old 4-second wait.
        # Keep Qt alive until the worker has closed its isolated child process.
        if self.thread is not None and self.thread.isRunning():
            if not getattr(self, '_close_pending', False):
                self._close_pending = True
                self.setEnabled(False)
                self._set_status('Modeller kapatılıyor…')
                self.worker.stop()
                self.thread.finished.connect(self.close)
                self.thread.quit()
            e.ignore()
            return
        self.s.save()
        if self.worker is not None:
            self.worker.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(4000)
        if self.hotkeys is not None:
            try:
                self.hotkeys.stop()
            except Exception:
                pass
        self.overlay.close()
        super().closeEvent(e)
        QGuiApplication.quit()
