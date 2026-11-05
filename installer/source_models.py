"""Reuse verified local models or restore them from the fixed central model depot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

from installer.manager import owned_path
from scripts.restore_packed_models import provision as provision_models

# Model bytes intentionally remain the original fixed model package.
MODEL_RELEASE = '0.5.0'
COPY_RESERVE = 256 * 1024**2


def normal_root(value):
    root = Path(value).absolute()
    for path in (root, *root.parents):
        reparse = path.exists() and bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
        if path.is_symlink() or reparse:
            raise ValueError('model klasöründe bağlantı/junction kullanılamaz')
    return root


def manifest_rows(path):
    data = path if isinstance(path, dict) else json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 1 or data.get('release') != MODEL_RELEASE:
        raise ValueError('kaynak model manifesti bu sürümle eşleşmiyor')
    rows = {}
    for component in data.get('components', {}).values():
        for row in component:
            name = row['path']
            if (not isinstance(name, str) or not name.startswith('models/') or '\\' in name or ':' in name
                    or '..' in Path(name).parts or type(row['bytes']) is not int or row['bytes'] < 0
                    or not re.fullmatch('[a-f0-9]{64}', row['sha256'])):
                raise ValueError('geçersiz sabit model girdisi')
            if name in rows and rows[name] != row:
                raise ValueError('çakışan model girdisi')
            rows[name] = row
    if not rows:
        raise ValueError('kaynak model manifesti boş')
    return list(rows.values())


def matches(path, row):
    try:
        if not path.is_file() or path.stat().st_size != row['bytes']:
            return False
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == row['sha256']
    except OSError:
        return False


def missing(root, rows):
    return [row for row in rows if not matches(owned_path(root, row['path']), row)]


def ensure_space(root, amount):
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < amount:
        raise RuntimeError('sabit model kurulumu için yeterli boş alan yok; en az ' + str((amount+1024**3-1)//1024**3) + ' gib gerekli')


def copy_verified(source, target, row):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.source-' + uuid.uuid4().hex)
    digest = hashlib.sha256()
    size = 0
    try:
        with source.open('rb') as inp, temporary.open('xb') as out:
            while block := inp.read(4 * 1024**2):
                size += len(block)
                if size > row['bytes']:
                    raise RuntimeError('kopyalanan model boyutu değişti')
                digest.update(block)
                out.write(block)
        if size != row['bytes'] or digest.hexdigest() != row['sha256']:
            raise RuntimeError('kopyalanan sabit model özeti eşleşmiyor')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def provision(target_root, installed_root, manifest, emit=print, packed_manifest=None):
    target = normal_root(target_root)
    installed = normal_root(installed_root)
    bundled = json.loads(Path(manifest).read_text(encoding='utf-8'))
    rows = manifest_rows(bundled)
    emit('kaynak için sabit model dosyaları doğrulanıyor')
    needed = missing(target, rows)
    if not needed:
        emit('kaynak model dosyaları zaten hazır; yeniden indirme yapılmadı')
        return {'copied': 0, 'downloaded': False, 'files': len(rows)}
    ensure_space(target, sum(row['bytes'] for row in needed) + COPY_RESERVE)
    # Validate every installed source path before copying any file. Invalid or
    # absent local files are repaired by the depot, never copied unchecked.
    local = [(row, owned_path(installed, row['path'])) for row in needed]
    available = [(row, path) for row, path in local if matches(path, row)]
    copied = 0
    for row, path in available:
        emit('doğrulanan yerel model kaynak klasörüne kopyalanıyor · '+str(copied+1)+'/'+str(len(available)))
        copy_verified(path, owned_path(target, row['path']), row)
        copied += 1
    downloaded = bool(missing(target, rows))
    if downloaded:
        packed_path = Path(packed_manifest) if packed_manifest is not None else Path(manifest).with_name('packed-models.json')
        packed = json.loads(packed_path.read_text(encoding='utf-8'))
        emit('eksik sabit modeller merkezi model deposundan tamamlanıyor')
        provision_models(target, packed, bundled, emit)
    # Never trust a successful recovery return without checking the model bytes.
    if missing(target, rows):
        raise RuntimeError('merkezi model deposundan sonra sabit modeller doğrulanamadı; kaynak kurulumu tamamlanmadı')
    emit('kaynak için sabit model dosyaları hazır')
    return {'copied': copied, 'downloaded': downloaded, 'files': len(rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--installed-root', type=Path)
    parser.add_argument('--packed-manifest', type=Path)
    args = parser.parse_args()
    installed = args.installed_root or Path(os.environ['LOCALAPPDATA'])/'mergen-next'
    try:
        provision(args.target_root, installed, args.manifest, packed_manifest=args.packed_manifest)
    except Exception as exc:
        print('kaynak model kurulumu tamamlanamadı: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
