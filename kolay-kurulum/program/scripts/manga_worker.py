"""Persistent isolated manga recognizer. JSON-lines stdin/stdout protocol.

Never imports Paddle or app.gpu_env. Model caches are shared, CUDA DLLs are not.
"""
import argparse
import base64
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.runtime_paths import configure_runtime
configure_runtime()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', choices=['auto', 'cuda', 'cpu'], default='auto')
    args = parser.parse_args()
    # Imported libraries may print progress; stdout belongs only to the protocol.
    protocol = sys.stdout
    sys.stdout = sys.stderr
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    import torch
    from PIL import Image
    from transformers import AutoTokenizer, ViTImageProcessor
    from manga_ocr.ocr import MangaOcrModel, post_process

    def reply(value):
        protocol.write(json.dumps(value, ensure_ascii=True)+'\n')
        protocol.flush()

    try:
        cuda = args.device != 'cpu' and torch.cuda.is_available()
        if args.device == 'cuda' and not cuda:
            raise RuntimeError('CUDA torch bulunamadı veya GPU kullanılamıyor.')
        device = 'cuda' if cuda else 'cpu'
        torch.set_num_threads(max(1, min(8, (os.cpu_count() or 4)//2)))
        path = 'kha-white/manga-ocr-base'
        processor = ViTImageProcessor.from_pretrained(path, local_files_only=True)
        tokenizer = AutoTokenizer.from_pretrained(path, tokenizer_type='bert-japanese', local_files_only=True)
        model = MangaOcrModel.from_pretrained(path, local_files_only=True).eval().to(device)
        if cuda:
            model.half()

        def stats():
            if not cuda:
                return {'allocated_mib': 0, 'reserved_mib': 0, 'peak_allocated_mib': 0, 'peak_reserved_mib': 0}
            torch.cuda.synchronize()
            return {k: round(v/1048576, 2) for k, v in {
                'allocated_mib': torch.cuda.memory_allocated(), 'reserved_mib': torch.cuda.memory_reserved(),
                'peak_allocated_mib': torch.cuda.max_memory_allocated(),
                'peak_reserved_mib': torch.cuda.max_memory_reserved()}.items()}

        reply({'ok': True, 'device': device, 'pid': os.getpid(), 'stats': stats()})
    except Exception as exc:
        reply({'ok': False, 'error': str(exc)})
        return
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get('op') == 'close':
                break
            if request.get('op') == 'stats':
                reply({'ok': True, 'stats': stats()})
                continue
            if request.get('op') != 'recognize':
                raise ValueError('Bilinmeyen manga-ocr isteği.')
            images = request.get('images', [])
            if len(images) > 4:
                raise ValueError('Tek istekte en fazla dört kırpım desteklenir.')
            if cuda:
                torch.cuda.reset_peak_memory_stats()
            pixels = []
            for encoded in images:
                raw = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width*image.height > 16000000:
                        raise ValueError('Kırpım çok büyük.')
                    pixels.append(processor(image.convert('L').convert('RGB'), return_tensors='pt').pixel_values[0])
            texts = []
            if pixels:
                batch = torch.stack(pixels).to(device=device, dtype=torch.float16 if cuda else torch.float32)
                with torch.inference_mode():
                    output = model.generate(batch, max_length=300)
                texts = [post_process(tokenizer.decode(tokens, skip_special_tokens=True)) for tokens in output.cpu()]
            reply({'ok': True, 'texts': texts, 'stats': stats()})
        except Exception as exc:
            reply({'ok': False, 'error': str(exc)})


if __name__ == '__main__':
    main()
