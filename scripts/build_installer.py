"""Compile the per-user installer with lowercase Turkish wizard messages."""
from pathlib import Path
import subprocess
import argparse
import json
import hashlib

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model-payload',type=Path,required=True)
    parser.add_argument('--packed-payload',type=Path,required=True)
    args=parser.parse_args();payload=args.model_payload.resolve();packed=args.packed_payload.resolve()
    archive_manifest=json.loads((ROOT/'assets/packed-models.json').read_text(encoding='utf-8'))
    for row in archive_manifest['files']:
        path=packed/row['archive']
        if not path.is_file() or path.stat().st_size!=row['archive_bytes']:raise ValueError('missing packed model')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=row['archive_sha256']:raise ValueError('packed model hash mismatch')
    if not (payload/'models/nllb-1.3b-baglam-v3/adapter-masked/adapter_model.safetensors').is_file():
        raise ValueError('fixed model payload is required')
    manifest=json.loads((ROOT/'assets/bundled-models.json').read_text(encoding='utf-8'))
    for rows in manifest['components'].values():
        for row in rows:
            path=(payload/row['path']).resolve()
            if not path.is_relative_to(payload) or not path.is_file() or path.stat().st_size!=row['bytes']:
                raise ValueError('model payload does not match the release manifest')
    if (ROOT/'dist/Mergen/_internal/assets/bundled-models.json').read_bytes()!=(ROOT/'assets/bundled-models.json').read_bytes():
        raise ValueError('the executable must include the current model manifest')
    compiler = ROOT / 'build-tools/inno/ISCC.exe'
    language = compiler.parent / 'Languages/Turkish.isl'
    # Keep section names, keys and compiler directives intact.
    lines = []
    for line in language.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith(';'):
            key, value = line.split('=', 1)
            line = key + '=' + value.replace('İ', 'i').lower()
        lines.append(line)
    (ROOT / 'build-tools/turkish-lowercase.isl').write_text('\n'.join(lines)+'\n', encoding='utf-8-sig')
    subprocess.run([str(compiler), '/DModelPayload='+str(payload), '/DPackedPayload='+str(packed), str(ROOT / 'installer/mergen-next.iss')], check=True)


if __name__ == '__main__':
    main()
