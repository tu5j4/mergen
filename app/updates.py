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
MAX_INSTALLER=600*1024*1024


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
    version(payload['version']);trusted_url(payload['url'])
    if not re.fullmatch('[a-f0-9]{64}',payload['sha256']): raise ValueError('Geçersiz dosya özeti')
    if not isinstance(payload['bytes'],int) or not 0<payload['bytes']<=MAX_INSTALLER: raise ValueError('Geçersiz paket boyutu')
    return payload


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
    trusted_url(payload['url'])
    folder=DATA_ROOT/'updates'/uuid.uuid4().hex;folder.mkdir(parents=True)
    temp=folder/'installer.part';target=folder/'mergen-kurulum.exe'
    digest=hashlib.sha256();received=0
    request=urllib.request.Request(payload['url'],headers={'User-Agent':'mergen/'+VERSION})
    try:
        with urllib.request.urlopen(request,timeout=30,context=tls_context()) as response,temp.open('wb') as out:
            while True:
                block=response.read(1024*1024)
                if not block:break
                received+=len(block)
                if received>payload['bytes'] or received>MAX_INSTALLER:raise ValueError('Paket beklenenden büyük')
                out.write(block);digest.update(block);emit(f'Güncelleme indiriliyor · {received*100//payload["bytes"]}%')
        if received!=payload['bytes'] or digest.hexdigest()!=payload['sha256']:raise ValueError('Paket bütünlüğü doğrulanamadı')
        temp.rename(target)
        return {'installer':str(target),'sha256':payload['sha256']}
    except Exception:
        temp.unlink(missing_ok=True);raise


def launch_update(package):
    if not getattr(sys,'frozen',False):raise RuntimeError('Güncelleme kurulumu yalnızca kurulu uygulamada çalışır.')
    subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(APP_ROOT/'installer/apply-update.ps1'),
        '-Installer',package['installer'],'-Sha256',package['sha256'],'-AppDirectory',str(INSTALL_ROOT),'-WaitPid',str(os.getpid())],
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
