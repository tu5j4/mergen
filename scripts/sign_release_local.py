"""Sign local release metadata; never copy or print a private key."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PublicFormat

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.storage import VERSION, REPOSITORY
from app.updates import verify


def sign(installer, key_path, output, notes):
    installer, output = Path(installer).resolve(), Path(output).resolve()
    if installer.name != f'mergen-setup-{VERSION}.exe' or not installer.is_file():
        raise ValueError('expected the current version installer')
    key = load_pem_private_key(Path(key_path).read_bytes(), password=None)
    pinned = (ROOT / 'assets/update-public-key.pem').read_bytes()
    if key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo) != pinned:
        raise ValueError('private key does not match the pinned public key')
    with installer.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    payload = dict(version=VERSION,
        url=f'https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{installer.name}',
        bytes=installer.stat().st_size, sha256=digest, notes=notes)
    parts=[]
    for part in sorted(installer.parent.glob(installer.stem+'-*.bin')):
        with part.open('rb') as stream:hashed=hashlib.file_digest(stream,'sha256').hexdigest()
        parts.append(dict(url=payload['url'].rsplit('/',1)[0]+'/'+part.name,bytes=part.stat().st_size,sha256=hashed))
    if parts:payload['parts']=parts
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    envelope = dict(payload=payload, signature=base64.b64encode(key.sign(canonical)).decode('ascii'))
    verify(envelope)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'mergen-update.json').write_text(json.dumps(envelope, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    checks = [(installer.name, payload['sha256']),
              ('mergen-update.json', hashlib.sha256((output/'mergen-update.json').read_bytes()).hexdigest())]
    checks += [(row['url'].rsplit('/',1)[-1],row['sha256']) for row in parts]
    (output / 'SHA256SUMS.txt').write_text(''.join(digest+'  '+name+'\n' for name,digest in checks), encoding='utf-8')
    return envelope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', required=True, type=Path)
    parser.add_argument('--installer', type=Path, default=ROOT/'release'/f'mergen-setup-{VERSION}.exe')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--notes', default='yeni arayüz ve logo, ekran paylaşımı düzenlemeleri, yerel intel xpu desteği ve sade kurulum. 0.2.0 için elle kurulum gerekir.')
    args = parser.parse_args()
    sign(args.installer, args.key, args.output or args.installer.parent, args.notes)
    print('güncelleme imzası ve dosya özetleri doğrulandı.')


if __name__ == '__main__':
    main()
