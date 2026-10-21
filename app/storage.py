"""Keep installed code, mutable data and model environments separate."""
import os
import sys
from pathlib import Path

APP_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
WORKER_ROOT = APP_ROOT / 'runtime-source' if getattr(sys, 'frozen', False) else APP_ROOT
INSTALL_ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else APP_ROOT
DATA_ROOT = Path(os.environ.get('MERGEN_DATA_DIR',
    Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'mergen-next'
    if getattr(sys, 'frozen', False) else APP_ROOT / '.data')).resolve()
VERSION = '0.3.1'
REPOSITORY = 'tu5j4/mergen'


def prepare_data():
    for name in ('models', 'envs', 'cache', 'logs', 'updates'):
        (DATA_ROOT / name).mkdir(parents=True, exist_ok=True)


def cache_environment():
    return dict(os.environ, PYTHONUTF8='1', HF_HOME=str(DATA_ROOT/'cache/huggingface'),
                HF_HUB_CACHE=str(DATA_ROOT/'cache/huggingface/hub'),
                PADDLE_PDX_CACHE_HOME=str(DATA_ROOT/'cache/paddlex'))
