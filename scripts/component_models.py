"""Resumable model downloads; publish only complete directories."""
import argparse
import json
import os
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.storage import DATA_ROOT
from app.runtime_paths import configure_runtime
from installer.catalog import COMPONENTS
from installer.manager import owned_path
configure_runtime()
_EVENT_LOCK=threading.Lock()


def phase(text):
    with _EVENT_LOCK:
        print('@mergen:'+json.dumps(dict(phase=text,progress=-1),ensure_ascii=True),flush=True)


def progress_class():
    from huggingface_hub.utils.tqdm import tqdm
    class Progress(tqdm):
        def __init__(self,*args,**kwargs):
            self._channel=kwargs.get('name','')
            self._sent=0
            self._began=time.monotonic()
            kwargs['disable']=False
            super().__init__(*args,**kwargs)
        def display(self,*args,**kwargs):
            if getattr(self,'_mergen_closed',False) or not self._channel.endswith('.transfer') or not hasattr(self,'n'):
                return True
            now=time.monotonic()
            if now-self._sent < .5 or self.n<1024:return True
            self._sent=now
            done=self.n/1024**2
            total=(self.total or 0)/1024**2
            rate=done/max(.001,now-self._began)
            phase(f'model indiriliyor · {done:.1f}/{total:.1f} mib · ortalama {rate:.1f} mib/sn')
            return True
        def close(self):
            self._mergen_closed=True
            super().close()
    return Progress


def download(repo,path,**kwargs):
    from huggingface_hub import snapshot_download
    phase('model kaynağına bağlanılıyor · tamamlanmamış indirmeler sürdürülüyor')
    snapshot_download(repo,local_dir=path,tqdm_class=progress_class(),**kwargs)
    phase('indirilen model dosyaları doğrulanıyor')


def model_lock(key):
    from filelock import FileLock
    path=owned_path(DATA_ROOT,Path('cache/model-downloads')/(key+'.lock'))
    path.parent.mkdir(parents=True,exist_ok=True)
    return FileLock(str(path),timeout=0)


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


def install_model(key):
    item=COMPONENTS[key]
    if item['kind']=='environment':raise ValueError('bu araç yalnız model indirir')
    staging=owned_path(DATA_ROOT,Path('cache/model-downloads')/key)
    with model_lock(key):
        staging.mkdir(parents=True,exist_ok=True)
        try:
            if item['kind']=='translation':
                hf=staging/'hf'
                download(item['repo'],hf,ignore_patterns=['*.h5','*.msgpack','*.ot','*.md','onnx/**','*.onnx','*.tflite'])
                if not (hf/'config.json').is_file() or not list(hf.glob('*.safetensors')) and not list(hf.glob('pytorch_model*.bin')):
                    raise RuntimeError('nllb ağırlıkları eksik')
                phase('nllb int8 biçimine dönüştürülüyor · bu aşama indirme değildir')
                from ctranslate2.converters import TransformersConverter
                from transformers import AutoTokenizer
                ct=staging/'ct2'
                TransformersConverter(str(hf)).convert(str(ct),quantization='int8',force=True)
                AutoTokenizer.from_pretrained(hf).save_pretrained(ct/'tokenizer')
                ready(hf);ready(ct)
                publish(hf,DATA_ROOT/'models'/(item['folder']+'-hf'))
                publish(ct,DATA_ROOT/'models'/(item['folder']+'-ct2'))
            elif item['kind']=='manga':
                path=staging/'manga'
                download(item['repo'],path,ignore_patterns=['*.md','*.h5','*.msgpack','*.onnx'])
                if not list(path.glob('*.safetensors')) and not list(path.glob('pytorch_model*.bin')): raise RuntimeError('manga-ocr ağırlıkları eksik')
                if not all((path/name).is_file() for name in ('config.json','vocab.txt','preprocessor_config.json')):raise RuntimeError('manga-ocr ayar veya sözlük dosyaları eksik')
                ready(path);publish(path,DATA_ROOT/'models/manga')
            else:
                pending=[]
                for name in item['names']:
                    path=staging/name;download('PaddlePaddle/'+name,path)
                    if item['family']=='transformers':
                        if not (path/'config.json').exists() or not list(path.glob('*.safetensors')):
                            raise RuntimeError(name+' için transformers ağırlıkları mevcut değil; bu bileşen kurulmadı.')
                    elif not (path/'inference.json').exists() or not (path/'inference.pdiparams').exists():
                        raise RuntimeError(name+' için paddle ağırlıkları eksik.')
                    ready(path);pending.append((path,DATA_ROOT/'models/ocr'/item['family']/name))
                for path,target in pending:publish(path,target)
        except Exception:
            phase('model hazırlanamadı · indirilen parçalar yeniden denemek için saklandı')
            raise
        else:
            if staging.exists():shutil.rmtree(staging)
    phase('model dosyaları doğrulandı ve hazırlandı')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('key',choices=[k for k,v in COMPONENTS.items() if v['kind']!='environment'])
    install_model(parser.parse_args().key)


if __name__=='__main__':main()
