"""Opt-in GitHub Releases updates; only pinned-key signed installers are accepted."""
import base64
import hashlib
import json
import os
import re
import ssl
import certifi
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from .storage import APP_ROOT, INSTALL_ROOT, DATA_ROOT, VERSION, REPOSITORY

MAX_MANIFEST=256*1024
MAX_INSTALLER=8*1024*1024*1024
MAX_PACKAGE=12*1024*1024*1024


def version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+',value): raise ValueError('Geçersiz sürüm numarası')
    return tuple(map(int,value.split('.')))


def trusted_url(value):
    u=urllib.parse.urlsplit(value)
    if u.scheme!='https' or u.netloc!='github.com' or not u.path.startswith('/'+REPOSITORY+'/releases/download/'):
        raise ValueError('Güncelleme adresi bu projenin GitHub sürümlerine ait değil.')
    return value


def tls_context():
    """Use bundled roots as well as Windows roots on fresh installations."""
    context=ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def request_json(url):
    request=urllib.request.Request(url,headers={'User-Agent':'mergen/'+VERSION,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=20,context=tls_context()) as response:
        raw=response.read(MAX_MANIFEST+1)
    if len(raw)>MAX_MANIFEST: raise ValueError('Güncelleme bildirimi çok büyük')
    return json.loads(raw)


def verify(envelope):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    payload=envelope['payload']
    public=load_pem_public_key((APP_ROOT/'assets/update-public-key.pem').read_bytes())
    public.verify(base64.b64decode(envelope['signature'],validate=True),
                  json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8'))
    package_files(payload)
    return payload


def package_files(payload):
    version(payload['version']);trusted_url(payload['url'])
    parts=payload.get('parts',[])
    if not isinstance(parts,list) or len(parts)>12:raise ValueError('geçersiz paket parçaları')
    files=[payload]+parts
    primary=urllib.parse.urlsplit(payload['url'])
    stem=Path(primary.path).stem
    seen=set()
    for index,row in enumerate(files):
        url=urllib.parse.urlsplit(trusted_url(row['url']))
        name=url.path.rsplit('/',1)[-1]
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+',name) or name in seen:raise ValueError('geçersiz paket adı')
        if index and (url.path.rsplit('/',1)[0]!=primary.path.rsplit('/',1)[0] or not re.fullmatch(re.escape(stem)+r'-\d+[a-z]?\.bin',name)):
            raise ValueError('paket parçası bu kuruluma ait değil')
        if not index and not name.endswith('.exe'):raise ValueError('kurulum exe olmalıdır')
        seen.add(name)
        if not re.fullmatch('[a-f0-9]{64}',row['sha256']):raise ValueError('geçersiz dosya özeti')
        if type(row['bytes']) is not int or not 0<row['bytes']<=MAX_INSTALLER:raise ValueError('geçersiz paket boyutu')
    if sum(row['bytes'] for row in files)>MAX_PACKAGE:raise ValueError('paket çok büyük')
    return files


def check():
    try: release=request_json('https://api.github.com/repos/'+REPOSITORY+'/releases/latest')
    except urllib.error.HTTPError as exc:
        if exc.code==404:return {'available':False,'message':'Henüz yayımlanmış güncelleme yok.'}
        raise
    if release.get('draft') or release.get('prerelease'):return {'available':False,'message':'Kararlı güncelleme yok.'}
    asset=next((a for a in release.get('assets',[]) if a['name']=='mergen-update.json'),None)
    if asset is None:return {'available':False,'message':'Bu sürüm için imzalı güncelleme paketi bulunamadı.'}
    payload=verify(request_json(trusted_url(asset['browser_download_url'])))
    available=version(payload['version'])>version(VERSION)
    return dict(payload,available=available,message=(payload.get('notes','') or 'Yeni sürüm hazır.') if available else 'Güncel sürümü kullanıyorsun.')


def download_update(payload,emit=print):
    if version(payload['version'])<=version(VERSION):raise ValueError('Eski sürüm kurulamaz')
    files=package_files(payload)
    folder=DATA_ROOT/'updates'/uuid.uuid4().hex;folder.mkdir(parents=True)
    total=sum(row['bytes'] for row in files);completed=0;checks=[]
    try:
        for row in files:
            name=urllib.parse.urlsplit(row['url']).path.rsplit('/',1)[-1]
            target=folder/name;temp=folder/(name+'.part')
            digest=hashlib.sha256();received=0
            request=urllib.request.Request(row['url'],headers={'User-Agent':'mergen/'+VERSION})
            with urllib.request.urlopen(request,timeout=30,context=tls_context()) as response,temp.open('wb') as out:
                while True:
                    from .operations import check_cancelled
                    check_cancelled()
                    block=response.read(1024*1024)
                    if not block:break
                    received+=len(block)
                    if received>row['bytes']:raise ValueError('paket beklenenden büyük')
                    out.write(block);digest.update(block);emit(f'güncelleme indiriliyor · {(completed+received)*100//total}%')
            if received!=row['bytes'] or digest.hexdigest()!=row['sha256']:raise ValueError('paket bütünlüğü doğrulanamadı')
            temp.rename(target);completed+=received
            checks.append(dict(name=name,sha256=row['sha256']))
        manifest=folder/'package.json'
        manifest.write_text(json.dumps(checks),encoding='utf-8')
        return {'installer':str(folder/checks[0]['name']),'sha256':payload['sha256'],
            'manifest':str(manifest),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}
    except Exception:
        for child in folder.iterdir():
            if child.is_file():child.unlink()
        raise


def launch_update(package):
    if not getattr(sys,'frozen',False):raise RuntimeError('Güncelleme kurulumu yalnızca kurulu uygulamada çalışır.')
    subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(APP_ROOT/'installer/apply-update.ps1'),
        '-Installer',package['installer'],'-Sha256',package['sha256'],'-AppDirectory',str(INSTALL_ROOT),'-WaitPid',str(os.getpid()),
        '-PackageManifest',package['manifest'],'-ManifestSha256',package['manifest_sha256']],
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
