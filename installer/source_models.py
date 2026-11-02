"""Fixed model file operations use stdlib; online recovery lazily verifies signed metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.parse
import uuid

from installer.manager import owned_path
from app.storage import VERSION, REPOSITORY

# Model bytes intentionally remain the original fixed model package.
MODEL_RELEASE = '0.5.0'
INSTALL_ARGUMENTS = ('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
BOOTSTRAP_SPACE = 20 * 1024**3
COPY_RESERVE = 256 * 1024**2


def normal_root(value):
    root = Path(value).absolute()
    for path in (root, *root.parents):
        reparse = path.exists() and bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
        if path.is_symlink() or reparse:
            raise ValueError('model klasöründe bağlantı/junction kullanılamaz')
    return root


def manifest_rows(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
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


def bootstrap_descriptor():
    # certifi/cryptography are required only for online recovery, after UI setup.
    from app import updates
    prefix = 'https://github.com/'+REPOSITORY+'/releases/download/v'+VERSION+'/'
    envelope = updates.request_json(updates.trusted_url(prefix+'mergen-update.json'))
    payload = updates.verify(envelope)
    if payload['version'] != VERSION:
        raise ValueError('kurulum bildirimi kaynak uygulama sürümüyle eşleşmiyor')
    files = updates.package_files(payload)
    release_directory = '/'+REPOSITORY+'/releases/download/v'+VERSION
    if any(urllib.parse.urlsplit(row['url']).path.rsplit('/', 1)[0] != release_directory for row in files):
        raise ValueError('kurulum dosyaları kaynak uygulama sürümüne ait değil')
    return files


def download_bootstrap(target, row):
    from app import updates
    if matches(target, row):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.download-' + uuid.uuid4().hex)
    try:
        request = urllib.request.Request(updates.trusted_url(row['url']), headers={'User-Agent': 'mergen-source-setup/'+VERSION})
        with urllib.request.urlopen(request, timeout=90, context=updates.tls_context()) as response, temporary.open('xb') as out:
            if not response.geturl().startswith('https://'):
                raise RuntimeError('kurulum indirmesi güvenli bağlantı kullanmıyor')
            size = 0
            while block := response.read(64 * 1024):
                size += len(block)
                if size > row['bytes']:
                    raise RuntimeError('kurulum başlatıcısı beklenenden büyük')
                out.write(block)
        if not matches(temporary, row):
            raise RuntimeError('kurulum başlatıcısının boyutu veya sha256 özeti eşleşmiyor')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def run_bootstrap(path):
    env = dict(os.environ)
    for key in ('MERGEN_DATA_DIR', 'PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'):
        env.pop(key, None)
    subprocess.run([str(path), *INSTALL_ARGUMENTS], env=env, check=True, timeout=7200)


def provision(target_root, installed_root, manifest, emit=print):
    target = normal_root(target_root)
    installed = normal_root(installed_root)
    rows = manifest_rows(manifest)
    emit('kaynak için sabit model dosyaları doğrulanıyor')
    needed = missing(target, rows)
    if not needed:
        emit('kaynak model dosyaları zaten hazır; kurulum tekrar çalıştırılmadı')
        return {'copied': 0, 'bootstrap': False, 'files': len(rows)}
    copy_bytes = sum(row['bytes'] for row in needed)
    ensure_space(target, copy_bytes + COPY_RESERVE)
    bootstrap = bool(missing(installed, needed))
    if bootstrap:
        # Reserve the installer/parts/archive peak plus the source copy if on one volume.
        same_volume = target.anchor.casefold() == installed.anchor.casefold()
        ensure_space(installed, BOOTSTRAP_SPACE + (copy_bytes if same_volume else 0))
        emit('sabit modeller eksik; bu uygulama sürümünün imzalı kurulum bildirimi doğrulanıyor')
        files = bootstrap_descriptor()
        installers = []
        for row in files:
            name = urllib.parse.urlsplit(row['url']).path.rsplit('/', 1)[-1]
            installer = owned_path(target, 'downloads/'+VERSION+'/'+name)
            download_bootstrap(installer, row)
            installers.append(installer)
        run_bootstrap(installers[0])
        # The published bootstrap may exit zero after cancel/error: never trust exit alone.
        if missing(installed, needed):
            raise RuntimeError('resmi kurulumdan sonra sabit modeller doğrulanamadı; kaynak kurulumu tamamlanmadı')
    copied = 0
    for row in needed:
        source = owned_path(installed, row['path'])
        destination = owned_path(target, row['path'])
        # Source hashes were checked before installation/copy; the atomic copy
        # checks them again while streaming, including changes after that check.
        emit('doğrulanan model kaynak klasörüne kopyalanıyor · '+str(copied+1)+'/'+str(len(needed)))
        copy_verified(source, destination, row)
        copied += 1
    if missing(target, rows):
        raise RuntimeError('kaynak model doğrulaması tamamlanamadı')
    emit('kaynak için sabit model dosyaları hazır')
    return {'copied': copied, 'bootstrap': bootstrap, 'files': len(rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target-root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--installed-root', type=Path)
    args = parser.parse_args()
    installed = args.installed_root or Path(os.environ['LOCALAPPDATA'])/'mergen-next'
    try:
        provision(args.target_root, installed, args.manifest)
    except Exception as exc:
        print('kaynak model kurulumu tamamlanamadı: '+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
