"""
Tüm modelleri bir kez indirir ve yerel klasöre hazırlar. Sonrasında uygulama internetsiz çalışır.

Kullanım:
    python scripts/download_models.py               # NLLB 600M (hızlı, ~650 MB)
    python scripts/download_models.py --large       # NLLB 1.3B (daha kaliteli, ~1.4 GB)
    python scripts/download_models.py --langs ja ko en
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import LANGS, MODELS_DIR  # noqa: E402

NLLB = {
    False: ("facebook/nllb-200-distilled-600M", "nllb-200-distilled-600M-ct2"),
    True: ("facebook/nllb-200-distilled-1.3B", "nllb-200-distilled-1.3B-ct2"),
}


def convert_nllb(large: bool) -> str:
    from ctranslate2.converters import TransformersConverter
    from transformers import AutoTokenizer

    hf_name, folder = NLLB[large]
    out = MODELS_DIR / folder
    if (out / "model.bin").is_file() and (out / "tokenizer" / "tokenizer_config.json").is_file():
        print(f"[nllb] zaten mevcut: {out}")
        return folder

    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[nllb] {hf_name} indiriliyor ve CTranslate2 int8 formatına çevriliyor…")
    print("       (bu adım için geçici olarak torch + transformers gerekir)")
    TransformersConverter(hf_name).convert(str(out), quantization="int8", force=True)
    AutoTokenizer.from_pretrained(hf_name).save_pretrained(str(out / "tokenizer"))
    print(f"[nllb] hazır: {out}")
    return folder


def warm_manga_ocr() -> None:
    print("[manga-ocr] model indiriliyor…")
    from manga_ocr import MangaOcr
    MangaOcr(force_cpu=True)


def warm_paddle_cjk(langs: list[str]) -> None:
    """Çince dikey metin motorunu kurulumda indir; ilk sayfada bekleme olmasın."""
    try:
        from app.gpu_env import setup_cuda_dll_paths
        setup_cuda_dll_paths()
        from paddleocr import PaddleOCR
        for lang in langs:
            print(f"[paddleocr] {LANGS[lang]['name']} dikey metin modeli indiriliyor…")
            PaddleOCR(
                lang={"zh_tw": "chinese_cht", "ja": "japan", "ko": "korean", "en": "en"}.get(lang, "ch"),
                ocr_version="PP-OCRv5",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                enable_mkldnn=False,
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="korean_PP-OCRv5_mobile_rec" if lang == 'ko' else "PP-OCRv5_mobile_rec",
            )
    except Exception as e:
        print(f"[paddleocr] atlandı: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--large", action="store_true", help="NLLB 1.3B modelini kullan")
    ap.add_argument('--ocr-only', action='store_true', help='Çeviri modelini/ayarlarını değiştirmeden yalnız OCR indir')
    ap.add_argument("--langs", nargs="+", default=list(LANGS.keys()),
                    choices=list(LANGS.keys()), help="OCR modelleri indirilecek diller")
    args = ap.parse_args()

    folder = convert_nllb(args.large) if not args.ocr_only else None
    if "ja" in args.langs:
        try:
            warm_manga_ocr()
        except Exception as e:
            print(f"[manga-ocr] atlandı: {e}")
    warm_paddle_cjk(args.langs)

    # Ayarlara seçilen modeli yaz
    from app.config import Settings
    s = Settings.load()
    if folder:
        s.translation_model = folder
        s.save()
    print("\nTamam! Artık 'python main.py' ile uygulamayı başlatabilirsiniz.")


if __name__ == "__main__":
    main()
