import os
from .storage import DATA_ROOT

def configure_runtime():
    os.environ['HF_HOME'] = str(DATA_ROOT / 'cache/huggingface')
    os.environ['HF_HUB_CACHE'] = str(DATA_ROOT / 'cache/huggingface/hub')
    os.environ['PADDLE_PDX_CACHE_HOME'] = str(DATA_ROOT / 'cache/paddlex')
