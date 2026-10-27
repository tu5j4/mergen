"""Split a full installer into GitHub-sized assets and compile its pinned launcher."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.storage import VERSION,REPOSITORY

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def build(installer,output,chunk_mib=400):
    installer=Path(installer).resolve();output=Path(output).resolve()
    if not installer.is_file() or installer.parent==output:raise ValueError('use a separate release output')
    output.mkdir(parents=True,exist_ok=True)
    if not 1<=chunk_mib<=2000:raise ValueError('chunk size must be between 1 and 2000 MiB')
    limit=chunk_mib*1024*1024
    parts=[]
    with installer.open('rb') as source:
        index=0
        while True:
            block=source.read(1024*1024)
            if not block:break
            index+=1;target=output/f'mergen-kurulum-{VERSION}-{index:02d}.data'
            hashed=hashlib.sha256();size=0
            with target.open('wb') as stream:
                while block:
                    stream.write(block);hashed.update(block);size+=len(block)
                    if size>=limit:break
                    block=source.read(min(1024*1024,limit-size))
            parts.append(dict(name=target.name,url=f'https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{target.name}',bytes=size,sha256=hashed.hexdigest()))
    manifest=dict(version=VERSION,sha256=digest(installer),bytes=installer.stat().st_size,parts=parts)
    metadata=output/'mergen-package.json'
    metadata.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    compiler=Path(os.environ['SystemRoot'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/codepage:65001','/target:winexe','/optimize+','/debug-',
        '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Runtime.Serialization.dll',
        '/win32icon:'+str(ROOT/'assets/mergen.ico'),'/resource:'+str(metadata)+',mergen.payload',
        '/out:'+str(output/f'mergen-setup-{VERSION}.exe'),str(ROOT/'installer/download-bootstrap.cs')],check=True)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--installer',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--chunk-mib',type=int,default=400)
    a=p.parse_args();print(json.dumps(build(a.installer,a.output,a.chunk_mib),indent=2))
