"""Opt-in isolated CUDA environment; does not replace the main Torch/Paddle."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    env = ROOT/'.manga-venv'
    python = env/('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.exists():
        subprocess.check_call([sys.executable, '-m', 'venv', str(env)])
    subprocess.check_call([str(python), '-m', 'pip', 'install', 'torch==2.11.0', 'torchvision==0.26.0',
                           '--index-url', 'https://download.pytorch.org/whl/cu128'])
    subprocess.check_call([str(python), '-m', 'pip', 'install', 'manga-ocr==0.1.16', 'transformers==5.19.0'])
    subprocess.check_call([str(python), '-c',
        "import torch; assert torch.cuda.is_available(), 'CUDA kullanilamiyor'; "
        "print(torch.__version__,torch.cuda.get_device_name()); print(torch.ones(1,device='cuda').item())"])
    # Download only the Japanese model; never change translation selection.
    subprocess.check_call([str(python), '-c',
        "from huggingface_hub import snapshot_download; snapshot_download('kha-white/manga-ocr-base')"])
    print('Izole manga-ocr GPU ortami hazir. Ana uygulama paketleri degismedi.')


if __name__ == '__main__':
    main()
