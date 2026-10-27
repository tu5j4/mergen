"""Lossless byte-lane compression; installed model files remain byte-identical."""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import lzma
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
CHUNK=32*1024*1024


def shuffle(data,width):return b''.join(data[index::width] for index in range(width))


def pack(source,target,width,workers=8,chunk=CHUNK):
    digest=hashlib.sha256()
    def compress(data):return lzma.compress(shuffle(data,width),preset=6)
    with ThreadPoolExecutor(max_workers=workers) as pool,source.open('rb') as stream,target.open('xb') as out:
        pending=deque()
        while data:=stream.read(chunk):
            digest.update(data);pending.append(pool.submit(compress,data))
            if len(pending)>=workers:out.write(pending.popleft().result())
        while pending:out.write(pending.popleft().result())
    return digest.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--models',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=8);p.add_argument('--resume',action='store_true');a=p.parse_args()
    if a.output.exists() and not a.resume:raise ValueError('choose a new archive folder')
    a.output.mkdir(parents=True,exist_ok=a.resume)
    previous=json.loads((ROOT/'assets/packed-models.json').read_text(encoding='utf-8'))['files'] if a.resume else []
    previous={row['path']:row for row in previous}
    paths=[('models/nllb-200-distilled-600M-hf/pytorch_model.bin',4),('models/nllb-1.3b-baglam-v3/base-bf16/model.safetensors',2),
           ('models/manga/pytorch_model.bin',4),('models/nllb-1.3b-baglam-v3/adapter-masked/adapter_model.safetensors',4)]
    manifest=json.loads((ROOT/'assets/bundled-models.json').read_text(encoding='utf-8'))
    original={r['path']:r for group in manifest['components'].values() for r in group}
    rows=[]
    for index,(relative,width) in enumerate(paths):
        source=a.models/relative;archive=a.output/f'weights-{index}.xz'
        if relative in previous:
            row=previous[relative]
            with archive.open('rb') as stream:valid=hashlib.file_digest(stream,'sha256').hexdigest()==row['archive_sha256']
            if not valid or row['sha256']!=original[relative]['sha256']:raise ValueError('existing archive mismatch')
            rows.append(row);continue
        hashed=pack(source,archive,width,workers=a.workers)
        assert hashed==original[relative]['sha256']
        with archive.open('rb') as stream:archive_hash=hashlib.file_digest(stream,'sha256').hexdigest()
        row=dict(original[relative],archive=archive.name,archive_bytes=archive.stat().st_size,
            archive_sha256=archive_hash,width=width,chunk=CHUNK)
        rows.append(row);print(json.dumps(row),flush=True)
    output=dict(schema=1,format='byte-lanes-xz-streams',files=rows)
    (ROOT/'assets/packed-models.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
