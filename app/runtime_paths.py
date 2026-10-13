"""Project-local model caches for installer-managed copies only."""
import os
from pathlib import Path


def configure_runtime():
    root = Path(__file__).resolve().parent.parent
    if (root / '.mergen-managed').is_file():
        # Intentionally owned by this installation, so uninstall never touches
        # another application's Hugging Face or Paddle cache.
        os.environ['HF_HOME'] = str(root / '.cache' / 'huggingface')
        os.environ['HF_HUB_CACHE'] = str(root / '.cache' / 'huggingface' / 'hub')
        os.environ['PADDLE_PDX_CACHE_HOME'] = str(root / '.cache' / 'paddlex')
