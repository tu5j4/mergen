"""Reading worker host. Settings, hotkeys and system usage belong to the controller.

This is an intentionally UI-less backend: QML is the only presentation layer.
It owns the overlay surfaces, the worker thread, the reading region and the
region selector. It never loads or saves settings on its own; the controller
passes its single ``Settings`` instance in ``__init__``.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QRect, QThread, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication

from ..config import Settings
from ..core.pipeline import TranslationWorker
from ..platform_utils import logical_to_capture_rect, logical_capture_plan
from .overlay import OverlayGroup
from .region_selector import RegionSelector


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


class ControlPanel(QObject):
    status_changed = Signal(str)
    running_changed = Signal(bool)
    devices_changed = Signal(str)
    region_changed = Signal(object)
    error = Signal(str)
    closed = Signal()
    runtime_adapter = Signal(dict)
    settings_changed = Signal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.s = settings
        self.worker: TranslationWorker | None = None
        self.thread: QThread | None = None
        self.running = False
        self.region: QRect | None = None
        self._selector: RegionSelector | None = None
        self._start_after_select = False
        self._closing = False
        self._closed = False
        self._finish_emitted = False

        self.overlay = OverlayGroup(settings)
        self.overlay.capture_areas_changed.connect(self._on_overlay_areas_changed)
        self.overlay.surfaces_changed.connect(self._on_surfaces_changed)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.overlay.set_region(screen.geometry())
        if settings.last_region and len(settings.last_region) == 4:
            self._apply_region(QRect(*settings.last_region), publish=False)
        self.overlay.setVisible(settings.overlay_visible)

    # ------------------------------------------------------------------ worker
    def _set_status(self, text: str) -> None:
        self.status_changed.emit(text)

    def _ensure_worker(self) -> None:
        if self.worker is not None or self._closing or self._closed:
            return
        self.thread = QThread(self)
        self.worker = TranslationWorker(
            self.s, self.overlay.is_capture_excluded(), self.overlay.winIds())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self._set_status)
        self.worker.runtime_adapter.connect(self.runtime_adapter.emit)
        self.worker.devices.connect(self.devices_changed.emit)
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
        if sys.platform == 'darwin':
            cap = logical_to_capture_rect(self.region)
        else:
            plan = logical_capture_plan(self.region)
            cap = plan if plan.needs_composition else plan.physical_bounds
        self.worker.set_region(cap, (self.region.width(), self.region.height()))

    def _on_hide_request(self, hidden: bool) -> None:
        if hidden:
            self.overlay.hide()
            QGuiApplication.processEvents()
            if self.worker:
                self.worker.ack_hidden()
        elif self.s.overlay_visible:
            self.overlay.show()

    def _on_overlay_areas_changed(self, areas) -> None:
        if self.worker:
            self.worker.set_overlay_areas(areas)

    def _on_surfaces_changed(self) -> None:
        if self.worker:
            self.worker.set_overlay_handles(self.overlay.winIds())
            self._push_region()

    def _on_worker_error(self, msg: str) -> None:
        self.running = False
        self.running_changed.emit(False)
        self._set_status(f"HATA: {msg}")
        self.error.emit(msg)

    # ------------------------------------------------------------------ actions
    def toggle_run(self) -> None:
        if self.region is None:
            self.select_region(start_after=True)
            return
        self._ensure_worker()
        if self.worker is None:
            return
        self.running = not self.running
        self.worker.set_active(self.running)
        self.running_changed.emit(self.running)
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
        if self.worker:
            self.worker.force_once()

    def toggle_overlay_visible(self) -> None:
        self.s.overlay_visible = not self.s.overlay_visible
        pending = self.worker is not None and bool(getattr(self.worker, '_tracking_pending', False))
        self.overlay.setVisible(self.s.overlay_visible and not pending)
        self.settings_changed.emit()

    def select_region(self, start_after: bool = False) -> None:
        if self._selector is not None or self._closing or self._closed:
            return
        self._start_after_select = start_after
        self.overlay.clear_blocks()
        self._selector = RegionSelector()
        self._selector.region_selected.connect(self._on_region_selected)
        self._selector.cancelled.connect(self._on_region_cancelled)
        self._selector.start()

    def _select_fullscreen(self) -> None:
        screen = QGuiApplication.screenAt(self.region.center()) if self.region is not None else None
        screen = screen or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            self._apply_region(screen.geometry())

    def _on_region_selected(self, rect: QRect) -> None:
        self._selector = None
        self._apply_region(rect)
        if self._start_after_select and not self.running:
            self.toggle_run()

    def _on_region_cancelled(self) -> None:
        self._selector = None

    def _apply_region(self, rect: QRect, publish: bool = True) -> None:
        self.region = QRect(rect)
        self.overlay.set_region(rect)
        if self.s.overlay_visible:
            self.overlay.show()
        self.overlay.flash_border(True)
        QTimer.singleShot(900, lambda: self.overlay.flash_border(False))
        self._push_region()
        if publish:
            self.region_changed.emit(QRect(rect))

    # ------------------------------------------------------------------ live settings
    def set_language(self, lang: str) -> None:
        self.s.source_lang = lang
        self.overlay.clear_blocks()
        if self.worker:
            self.worker.set_language(lang)

    def apply_ocr_engine(self, engine: str) -> None:
        self.s.ocr_engine = engine
        self.overlay.clear_blocks()
        if self.worker:
            self.worker.set_ocr_engine(engine)
            self.worker.force_once()
        self._set_status("OCR motoru değişti; yeni motor yükleniyor…")

    def apply_paddle_model(self, mobile: bool) -> None:
        self.s.paddle_mobile = bool(mobile)
        if self.worker and self.s.ocr_engine in ("auto", "paddleocr"):
            self.worker.set_ocr_engine(self.s.ocr_engine)
            self.worker.force_once()
        self._set_status("PaddleOCR modeli değişti; sonraki taramada kullanılacak.")

    def apply_bubble_detection(self, enabled: bool) -> None:
        self.s.bubble_detection = bool(enabled)
        if self.worker and self.s.ocr_engine in ("auto", "paddleocr"):
            self.worker.set_ocr_engine(self.s.ocr_engine)
            self.worker.force_once()

    def apply_manga_device(self, device: str) -> None:
        self.s.manga_device = device
        if self.worker and self.s.source_lang == 'ja':
            self.worker.set_ocr_engine(self.s.ocr_engine)
            self.worker.force_once()
        self._set_status('manga-ocr cihazı değişti; izole yardımcı işlem yeniden yüklenecek.')

    def apply_manga_enabled(self, enabled: bool) -> None:
        self.s.use_manga_ocr = bool(enabled)
        if self.worker and self.s.source_lang == 'ja' and self.s.ocr_engine == 'auto':
            self.worker.set_ocr_engine(self.s.ocr_engine)
            self.worker.force_once()

    def apply_chinese_translation(self, via_english: bool) -> None:
        self.s.chinese_translation_via_english = bool(via_english)
        if self.worker:
            self.worker.force_once()
        self._set_status("Çince çeviri yolu değişti; sonraki taramada uygulanacak.")

    def apply_preset(self, name: str) -> None:
        self.s.apply_preset(name)
        self.settings_changed.emit()

    def apply_visual(self) -> None:
        self.overlay.refresh_style()

    def apply_scroll_tracking(self, enabled: bool) -> None:
        self.s.scroll_tracking = bool(enabled)
        if self.worker:
            self.worker.set_scroll_tracking(self.s.scroll_tracking)

    def clear_context(self) -> None:
        self.overlay.clear_blocks()
        if self.worker is not None:
            self.worker.reset_translation_context()
        self._set_status('konuşma hafızası temizlendi')

    def reset_context_enabled(self, enabled: bool) -> None:
        if self.worker is not None:
            self.worker.reset_translation_context(enabled)

    # ------------------------------------------------------------------ shutdown
    def shutdown(self) -> None:
        if self._closing or self._closed:
            return
        self._closing = True
        if self.running:
            self.running = False
            self.running_changed.emit(False)
        if self._selector is not None:
            try:
                self._selector.close()
            except Exception:
                pass
            self._selector = None
        thread = self.thread
        if thread is not None and thread.isRunning():
            thread.finished.connect(self._finalize_close)
            if self.worker is not None:
                self.worker.stop()
            thread.quit()
        else:
            self._finalize_close()

    def _finalize_close(self) -> None:
        if self._finish_emitted:
            return
        self._finish_emitted = True
        self._closed = True
        self._closing = False
        self.overlay.close()
        self.worker = None
        self.thread = None
        self.closed.emit()

    def close(self) -> None:
        self.shutdown()
