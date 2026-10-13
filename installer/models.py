"""One explicitly selected model download per invocation; errors propagate."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('component', choices=['paddle', 'korean', 'server', 'manga', '600m', '1300m'])
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()
    from app.runtime_paths import configure_runtime
    configure_runtime()
    if args.component in ('600m', '1300m'):
        from scripts.download_models import convert_nllb
        from app.config import Settings
        folder = convert_nllb(args.component == '1300m')
        settings = Settings.load()
        settings.translation_model = folder
        settings.save()
    elif args.component == 'manga':
        from huggingface_hub import snapshot_download
        snapshot_download('kha-white/manga-ocr-base')
    else:
        from app.gpu_env import setup_cuda_dll_paths
        setup_cuda_dll_paths()
        from app.config import Settings
        from app.core.ocr import OCREngine
        import numpy as np
        settings = Settings(ocr_engine='paddleocr', use_manga_ocr=False,
                            paddle_mobile=args.component != 'server',
                            use_gpu='no' if args.cpu else 'auto')
        engine = OCREngine('ko' if args.component == 'korean' else 'zh', settings)
        try:
            engine.process(np.full((64, 256, 3), 255, np.uint8))
        finally:
            engine.close()
    print('seçilen model hazır.')


if __name__ == '__main__':
    main()
