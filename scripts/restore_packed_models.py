"""Restore model bytes using only the installer's bundled Python standard library."""
import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path
import sys
import uuid
import re
import shutil
import urllib.request
import urllib.parse
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from installer.manager import owned_path

MODEL_PREFIX = 'https://github.com/tu5j4/nllb-mergen-baglam-v1/releases/download/'


def matches(path, size, digest):
    if not path.is_file() or path.stat().st_size != size:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == digest


class SecureRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('model indirmesi güvenli bağlantı kullanmıyor')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(root, row, emit=print):
    url = row['url']
    parsed = urllib.parse.urlsplit(url)
    if (not url.startswith(MODEL_PREFIX) or parsed.query or parsed.fragment
            or any(part in ('.', '..') for part in parsed.path.split('/'))
            or '%' in parsed.path or '\\' in url
            or type(row['archive_bytes']) is not int or row['archive_bytes'] <= 0
            or not re.fullmatch('[a-f0-9]{64}', row['archive_sha256'])):
        raise ValueError('geçersiz sabit model indirmesi')
    target = owned_path(root, Path('model-archives') / row['archive'])
    if matches(target, row['archive_bytes'], row['archive_sha256']):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.download-' + uuid.uuid4().hex)
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'mergen-models/0.5.0'})
        emit('sabit model indiriliyor · ' + row['archive'])
        size = 0
        digest = hashlib.sha256()
        opener = urllib.request.build_opener(SecureRedirect())
        with opener.open(request, timeout=90) as inp, temporary.open('xb') as out:
            if urllib.parse.urlsplit(inp.geturl()).scheme != 'https':
                raise ValueError('model indirmesi güvenli bağlantı kullanmıyor')
            while block := inp.read(1024 * 1024):
                size += len(block)
                if size > row['archive_bytes']:
                    raise ValueError('model arşivi beklenenden büyük')
                digest.update(block)
                out.write(block)
        if size != row['archive_bytes'] or digest.hexdigest() != row['archive_sha256']:
            raise ValueError('model indirme özeti eşleşmedi')
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def normal_root(root):
    root = Path(root).absolute()
    for parent in (root, *root.parents):
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('model kökünde bağlantı/junction kullanılamaz')
    return root


def provision(root, manifest, bundle, emit=print):
    """Reuse verified installed files; download pinned model assets independently of app releases."""
    root = normal_root(root)
    if bundle.get('schema') != 1 or bundle.get('release') != '0.5.0':
        raise ValueError('sabit model sürümü eşleşmiyor')
    if manifest.get('schema') != 1 or manifest.get('format') != 'byte-lanes-xz-streams':
        raise ValueError('geçersiz model arşivi')
    rows = {}
    for component in bundle['components'].values():
        for row in component:
            name = row['path']
            if (not name.startswith('models/') or '\\' in name or ':' in name
                    or type(row['bytes']) is not int or row['bytes'] < 0
                    or not re.fullmatch('[a-f0-9]{64}', row['sha256'])):
                raise ValueError('geçersiz model girdisi')
            owned_path(root, name)
            if name in rows and rows[name] != row:
                raise ValueError('çakışan model girdisi')
            rows[name] = row
    if not rows:
        raise ValueError('model listesi boş')
    packed = {row['path']: row for row in manifest['files']}
    if len(packed) != len(manifest['files']):
        raise ValueError('tekrarlanan sıkıştırılmış model girdisi')
    for name, row in packed.items():
        if name not in rows or any(row[k] != rows[name][k] for k in ('bytes', 'sha256')):
            raise ValueError('sıkıştırılmış model bildirimi eşleşmiyor')
    needed = {name: row for name, row in rows.items() if not matches(owned_path(root, name), row['bytes'], row['sha256'])}
    if not needed:
        emit('sabit model dosyaları zaten hazır; indirme yapılmadı')
        return
    root.mkdir(parents=True, exist_ok=True)
    required = sum(row['bytes'] for row in needed.values()) + max(
        [row['archive_bytes'] for name, row in packed.items() if name in needed] + [manifest['support']['archive_bytes']]) + 256 * 1024**2
    if shutil.disk_usage(root).free < required:
        raise RuntimeError('sabit modeller için yeterli boş alan yok')
    support = {name: row for name, row in rows.items() if name not in packed}
    if support.keys() & needed.keys():
        archive = download(root, manifest['support'], emit)
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if len(entries) != len(support) or {entry.filename for entry in entries} != support.keys():
                raise ValueError('model destek arşivi dosya listesi eşleşmiyor')
            for entry in entries:
                row = support[entry.filename]
                if entry.file_size != row['bytes']:
                    raise ValueError('model destek dosyası boyutu eşleşmiyor')
                if entry.filename not in needed:
                    continue
                target = owned_path(root, entry.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.restore-' + uuid.uuid4().hex)
                try:
                    digest = hashlib.sha256()
                    size = 0
                    with zipped.open(entry) as inp, temporary.open('xb') as out:
                        while block := inp.read(1024 * 1024):
                            size += len(block)
                            if size > row['bytes']:
                                raise ValueError('model destek dosyası beklenenden büyük')
                            digest.update(block)
                            out.write(block)
                    if size != row['bytes'] or digest.hexdigest() != row['sha256']:
                        raise ValueError('model destek dosyası özeti eşleşmedi')
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
        archive.unlink()
    for name, row in packed.items():
        if name in needed:
            download(root, row, emit)
            restore(root, dict(schema=1, format=manifest['format'], files=[row]), emit)
    if any(not matches(owned_path(root, name), row['bytes'], row['sha256']) for name, row in rows.items()):
        raise ValueError('sabit model doğrulaması tamamlanamadı')
    emit('tüm sabit model dosyaları doğrulandı')


def unshuffle(data,width):
    output=bytearray(len(data));offset=0
    for index in range(width):
        length=(len(data)+width-1-index)//width
        output[index::width]=data[offset:offset+length];offset+=length
    return output


def restore(root,manifest,emit=print):
    if manifest['schema']!=1 or manifest['format']!='byte-lanes-xz-streams':raise ValueError('geçersiz model arşivi')
    for row in manifest['files']:
        if row['width'] not in (2,4) or not 1<=row['chunk']<=64*1024*1024 or row['bytes']<=0:
            raise ValueError('geçersiz model arşivi boyutu')
        archive=owned_path(root,Path('model-archives')/row['archive'])
        target=owned_path(root,row['path'])
        if matches(target,row['bytes'],row['sha256']):
            continue
        if archive.stat().st_size!=row['archive_bytes']:raise ValueError('model arşivi eksik')
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=row['archive_sha256']:raise ValueError('model arşivi bozuk')
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=owned_path(root,target.relative_to(root).with_name(target.name+'.restore-'+uuid.uuid4().hex))
        digest=hashlib.sha256();size=0
        try:
            with lzma.open(archive,'rb') as stream,temporary.open('xb') as out:
                while data:=stream.read(row['chunk']):
                    data=unshuffle(data,row['width']);size+=len(data)
                    if size>row['bytes']:raise ValueError('model beklenenden büyük')
                    digest.update(data);out.write(data)
                    emit('model dosyası hazırlanıyor · '+str(size*100//row['bytes'])+'%')
            if size!=row['bytes'] or digest.hexdigest()!=row['sha256']:raise ValueError('model özeti eşleşmedi')
            os.replace(temporary,target)
            archive.unlink()
        finally:temporary.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--bundled-manifest',type=Path)
    a=p.parse_args();root=normal_root(a.data_root);root.mkdir(parents=True,exist_ok=True)
    logs=owned_path(root,'logs');logs.mkdir(exist_ok=True)
    with owned_path(root,'logs/model-restore.log').open('w',encoding='utf-8') as log:
        try:
            manifest=json.loads(a.manifest.read_text(encoding='utf-8'))
            emit=lambda s: (log.write(s+'\n'),log.flush())
            if 'support' in manifest:
                if not a.bundled_manifest:raise ValueError('sabit model bildirimi gerekli')
                provision(root,manifest,json.loads(a.bundled_manifest.read_text(encoding='utf-8')),emit)
            else:
                restore(root,manifest,emit)
            if a.bundled_manifest:
                bundle=json.loads(a.bundled_manifest.read_text(encoding='utf-8'))
                for rows in bundle['components'].values():
                    for row in rows:
                        target=owned_path(root,row['path'])
                        if not target.is_file() or target.stat().st_size!=row['bytes']:
                            raise ValueError('kurulum model dosyası eksik: '+row['path'])
                        with target.open('rb') as stream:
                            if hashlib.file_digest(stream,'sha256').hexdigest()!=row['sha256']:
                                raise ValueError('kurulum model özeti eşleşmedi: '+row['path'])
                log.write('tüm sabit model dosyaları doğrulandı\n')
        except Exception:
            import traceback
            log.write(traceback.format_exc());raise


if __name__=='__main__':main()
