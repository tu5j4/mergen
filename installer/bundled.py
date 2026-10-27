"""Fixed release models. Never replace a trained package with Hub 'main'."""
import hashlib
import json
from pathlib import Path
from app.storage import APP_ROOT
from .manager import owned_path


def entries(key):
    path=APP_ROOT/'assets/bundled-models.json'
    if not path.is_file():return []
    return json.loads(path.read_text(encoding='utf-8'))['components'].get(key,[])


def check_component(key, root):
    rows=entries(key)
    if not rows:return False
    try:
        return all((p:=owned_path(root,row['path'])).is_file() and p.stat().st_size==row['bytes'] for row in rows)
    except (OSError,ValueError):return False


def verify_component(key, root, emit=print):
    rows=entries(key)
    if not rows or not check_component(key,root):
        raise RuntimeError('model kurulum paketine aittir; eksik dosyaları tamamlamak için bu sürümün kurulumunu yeniden çalıştırın.')
    from app.operations import check_cancelled
    for index,row in enumerate(rows):
        check_cancelled()
        emit(f'paketteki model doğrulanıyor · {index+1}/{len(rows)}')
        digest=hashlib.sha256()
        with owned_path(root,row['path']).open('rb') as stream:
            while block:=stream.read(4*1024*1024):
                check_cancelled();digest.update(block)
        if digest.hexdigest()!=row['sha256']:
            raise RuntimeError('model dosyası sürüm paketiyle eşleşmiyor; bu sürümün kurulumunu yeniden çalıştırın.')
    emit('paketteki model dosyaları doğrulandı')
