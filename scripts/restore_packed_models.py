"""Restore model bytes using only the installer's bundled Python standard library."""
import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from installer.manager import owned_path


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
    a=p.parse_args();root=a.data_root.resolve();root.mkdir(parents=True,exist_ok=True)
    logs=root/'logs';logs.mkdir(exist_ok=True)
    with (logs/'model-restore.log').open('w',encoding='utf-8') as log:
        try:restore(root,json.loads(a.manifest.read_text(encoding='utf-8')),lambda s:log.write(s+'\n'))
        except Exception:
            import traceback
            log.write(traceback.format_exc());raise


if __name__=='__main__':main()
