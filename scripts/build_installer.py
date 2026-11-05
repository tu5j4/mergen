"""Compile the per-user installer with lowercase Turkish wizard messages."""
from pathlib import Path
import subprocess
import argparse
import json
import hashlib

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser()
    parser.parse_args()
    archive_manifest=json.loads((ROOT/'assets/packed-models.json').read_text(encoding='utf-8'))
    for row in archive_manifest['files']:
        if not row.get('url','').startswith('https://github.com/tu5j4/nllb-mergen-baglam-v1/releases/download/'):
            raise ValueError('a pinned central model URL is required')
    if 'support' not in archive_manifest:raise ValueError('central support package is required')
    for name in ('bundled-models.json','packed-models.json'):
        if (ROOT/'dist/Mergen/_internal/assets'/name).read_bytes()!=(ROOT/'assets'/name).read_bytes():
            raise ValueError('the executable must include the current model manifests')
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
    subprocess.run([str(compiler), str(ROOT / 'installer/mergen-next.iss')], check=True)


if __name__ == '__main__':
    main()
