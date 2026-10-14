"""Download to staging, verify required files, publish only complete model directories."""
import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.storage import DATA_ROOT
from app.runtime_paths import configure_runtime
from installer.catalog import COMPONENTS
from installer.manager import owned_path
configure_runtime()


def ready(path):
    (path/'mergen-ready.json').write_text('{"complete":true}',encoding='utf-8')


def publish(staged,target):
    target=owned_path(DATA_ROOT,target.relative_to(DATA_ROOT))
    backup=target.with_name(target.name+'.previous-'+uuid.uuid4().hex)
    if target.exists(): target.rename(backup)
    try:
        target.parent.mkdir(parents=True,exist_ok=True);staged.rename(target)
    except Exception:
        if backup.exists(): backup.rename(target)
        raise
    if backup.exists(): shutil.rmtree(backup)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('key',choices=list(COMPONENTS));args=parser.parse_args()
    item=COMPONENTS[args.key]
    staging=DATA_ROOT/'models'/('.staging-'+uuid.uuid4().hex);staging.mkdir(parents=True)
    from huggingface_hub import snapshot_download
    try:
        if item['kind']=='translation':
            hf=staging/'hf';snapshot_download(item['repo'],local_dir=hf,ignore_patterns=['*.h5','*.msgpack','*.ot','*.md'])
            if not (hf/'config.json').is_file() or not list(hf.glob('*.safetensors')) and not list(hf.glob('pytorch_model*.bin')):
                raise RuntimeError('NLLB ağırlıkları eksik')
            from ctranslate2.converters import TransformersConverter
            from transformers import AutoTokenizer
            ct=staging/'ct2';TransformersConverter(str(hf)).convert(str(ct),quantization='int8')
            AutoTokenizer.from_pretrained(hf).save_pretrained(ct/'tokenizer')
            ready(hf);ready(ct)
            publish(hf,DATA_ROOT/'models'/(item['folder']+'-hf'))
            publish(ct,DATA_ROOT/'models'/(item['folder']+'-ct2'))
        elif item['kind']=='manga':
            path=staging/'manga';snapshot_download(item['repo'],local_dir=path,ignore_patterns=['*.md','*.h5','*.msgpack'])
            if not list(path.glob('*.safetensors')) and not list(path.glob('pytorch_model*.bin')): raise RuntimeError('manga-ocr ağırlıkları eksik')
            if not all((path/name).is_file() for name in ('config.json','vocab.txt','preprocessor_config.json')):raise RuntimeError('manga-ocr ayar veya sözlük dosyaları eksik')
            ready(path);publish(path,DATA_ROOT/'models/manga')
        else:
            pending=[]
            for name in item['names']:
                path=staging/name;snapshot_download('PaddlePaddle/'+name,local_dir=path)
                if item['family']=='transformers':
                    if not (path/'config.json').exists() or not list(path.glob('*.safetensors')):
                        raise RuntimeError(name+' için Transformers ağırlıkları mevcut değil; bu bileşen kurulmadı.')
                elif not (path/'inference.json').exists() or not (path/'inference.pdiparams').exists():
                    raise RuntimeError(name+' için Paddle ağırlıkları eksik.')
                ready(path);pending.append((path,DATA_ROOT/'models/ocr'/item['family']/name))
            for path,target in pending: publish(path,target)
        print('Model dosyaları doğrulandı ve hazırlandı.')
    finally:
        if staging.exists(): shutil.rmtree(staging)

if __name__=='__main__': main()
