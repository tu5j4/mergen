"""
Ayarlar ve dil tanımları.
Bu dosya UI'dan bağımsızdır -> ileride mobil porta aynen taşınabilir mantık.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from .runtime_paths import configure_runtime

configure_runtime()

from .storage import APP_ROOT, DATA_ROOT
PROJECT_ROOT = APP_ROOT
APP_ICON = PROJECT_ROOT / 'assets' / ('mergen.ico' if sys.platform == 'win32' else 'mergen-logo.png')
SETTINGS_FILE = DATA_ROOT / "settings.json"
MODELS_DIR = DATA_ROOT / "models"
SETTINGS_VERSION = 7

TARGET_NLLB = "tur_Latn"  # Hedef dil: Türkçe

TRANSLATION_MODELS = {
    "nllb-200-distilled-600M-ct2": "Standart — hızlı, 4 GB VRAM önerilir",
    "nllb-200-distilled-1.3B-ct2": "Kaliteli — daha doğal, 6 GB+ VRAM önerilir",
}

LANGS: dict[str, dict] = {
    "ja": {"name": "Japonca (Manga)", "nllb": "jpn_Jpan",
           "joiner": "", "vertical_rtl": True},
    "ko": {"name": "Korece (Manhwa / Webtoon)", "nllb": "kor_Hang",
           "joiner": " ", "vertical_rtl": False},
    "zh": {"name": "Çince Basit (Manhua)", "nllb": "zho_Hans",
           "joiner": "", "vertical_rtl": True},
    "zh_tw": {"name": "Çince Geleneksel (Manhua)", "nllb": "zho_Hant",
              "joiner": "", "vertical_rtl": True},
    "en": {"name": "İngilizce (Çizgi roman / Scan)", "nllb": "eng_Latn",
           "joiner": " ", "vertical_rtl": False},
}

# Hız / kalite ön ayarları
PRESETS: dict[str, dict] = {
    "fast":     {"ocr_canvas_size": 1280, "ocr_mag_ratio": 1.0, "beam_size": 1, "settle_ms": 120},
    "balanced": {"ocr_canvas_size": 1600, "ocr_mag_ratio": 1.2, "beam_size": 2, "settle_ms": 180},
    "quality":  {"ocr_canvas_size": 2560, "ocr_mag_ratio": 1.6, "beam_size": 4, "settle_ms": 200},
}
PRESET_NAMES = {"fast": "Hızlı", "balanced": "Dengeli", "quality": "Kaliteli (GPU önerilir)"}


@dataclass
class Settings:
    settings_version: int = SETTINGS_VERSION
    source_lang: str = "en"
    speed_preset: str = "balanced"

    # Takip
    poll_ms: int = 60               # ekran ne sıklıkla kontrol edilsin (kaydırma takibi)
    settle_ms: int = 220            # kaydırma durduktan kaç ms sonra OCR başlasın
    change_threshold: float = 3.0   # sayfa değişti mi eşiği (0-255 ortalama fark)
    scroll_tracking: bool = True    # kaydırmayı takip et, çeviriyi kaydır, sadece yeni kısmı oku

    # OCR
    use_gpu: str = "auto"           # "auto" | "yes" | "no"
    use_manga_ocr: bool = True
    use_paddle_cjk: bool = True   # Çince dikey metin için PP-OCRv5
    paddle_mobile: bool = True    # hızlı mobil PaddleOCR modelleri
    ocr_engine: str = "auto"      # auto | manga_ocr | paddleocr
    manga_device: str = "auto"    # auto | cuda | cpu; persistent isolated process
    min_confidence: float = 0.25
    ocr_mag_ratio: float = 1.0
    ocr_canvas_size: int = 1408
    ocr_batch: int = 8
    manga_batch: int = 4
    group_gap_ratio: float = 0.65
    min_box_size: int = 8
    bubble_detection: bool = True  # konuşma balonu sınırlarını gruplamada kullan
    bubble_min_area: int = 900
    # Yoğun Japonca metin: balonu sütunlara/satırlara bölüp ayrı ayrı oku
    ja_dense_split: bool = True
    ja_dense_ratio: float = 11.0    # (uzun kenar / karakter boyu) bundan büyükse böl
    ja_seg_chars: float = 9.0       # bir parçada en fazla ~kaç karakter olsun

    # Çeviri
    translation_model: str = "nllb-200-distilled-600M-ct2"
    beam_size: int = 3             # doğal/kararlı Türkçe için hız-kalite dengesi
    chinese_translation_via_english: bool = False
    translate_chunk: int = 3        # kaç balon çevrilince ekrana bassın (aşamalı gösterim)
    cache_size: int = 4000
    session_context: bool = True   # RAM-only names/terms and recent dialogue

    # Görünüm
    overlay_opacity: float = 0.93
    font_family: str = "Segoe UI"
    font_bold: bool = True
    max_font_px: int = 40
    min_font_px: int = 9
    box_padding: int = 4
    overlay_visible: bool = True
    share_translations: bool = True
    theme: str = "navy"
    panel_theme: str = "white"
    translation_backend: str = "local"
    ocr_backend: str = "local"
    manga_backend: str = "local"
    check_updates: bool = True
    show_system_usage: bool = True
    show_gpu_usage: bool = False
    show_vram_usage: bool = False
    show_cpu_usage: bool = False
    usage_preferences_set: bool = False

    last_region: list | None = None

    # ------------------------------------------------------------------
    @property
    def model_path(self) -> Path:
        return MODELS_DIR / self.translation_model

    def apply_preset(self, name: str) -> None:
        if name in PRESETS:
            self.speed_preset = name
            for k, v in PRESETS[name].items():
                setattr(self, k, v)

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        old_version = SETTINGS_VERSION
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                old_version = int(data.get("settings_version", 1))
                valid = {f.name for f in fields(cls)}
                for k, v in data.items():
                    if k in valid:
                        setattr(s, k, v)
            except Exception as e:
                print(f"[ayarlar] okunamadı: {e}")
        if old_version < SETTINGS_VERSION:
            # Eski (yavaş) ayarlardan geçiş
            s.settings_version = SETTINGS_VERSION
            if old_version < 3:
                s.beam_size = 3
            if old_version < 4:
                s.theme = "navy"
            if old_version < 5:
                s.ocr_engine = "auto"
            if old_version < 6:
                s.paddle_mobile = True
        if not s.usage_preferences_set:
            s.show_gpu_usage = s.show_vram_usage = s.show_cpu_usage = False
        s.panel_theme = {"glass_dark": "green", "glass_light": "white"}.get(s.panel_theme, s.panel_theme)
        if s.panel_theme not in ("green", "white", "navy", "black", "sepia"):
            s.panel_theme = "green"
        if s.source_lang not in LANGS:
            s.source_lang = "en"
        if s.ocr_engine not in ('auto', 'manga_ocr', 'paddleocr'):
            s.ocr_engine = 'auto'
        if s.manga_device not in ('auto', 'cuda', 'cpu'):
            s.manga_device = 'auto'
        return s

    def save(self) -> None:
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"[ayarlar] kaydedilemedi: {e}")
