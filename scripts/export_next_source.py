"""Export a reviewed source allowlist; runtime data and private keys never ship."""
import argparse
import hashlib
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = {'app': {'.py', '.qml', '.json'}, 'assets': {'.png', '.ico', '.svg', '.pem', '.json'},
         'installer': {'.py', '.iss', '.ps1', '.txt', '.cs'}, 'scripts': {'.py', '.ps1'},
         'tests': {'.py'}, 'docs': {'.md'}, '.github': {'.yml', '.yaml'}}
FILES = ('AGENTS.md', 'main.py', 'next_main.py', 'baslat.bat', 'kurulum.bat',
         'requirements.txt', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
         '.gitignore', '.gitattributes')
SKIP = {'install_test_cpu.py', 'verify_local_models.py', 'diagnose_bundle.py', 'publish_local_copy.ps1'}
SECRET = re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{24,}')
PERSONAL = re.compile(rb'[A-Za-z]:[\\/]Users[\\/][^\\/\r\n]+', re.I)


def source_files(source=ROOT):
    source = Path(source).resolve()
    paths = [source / name for name in FILES]
    for folder, extensions in TREES.items():
        paths += [p for p in (source / folder).rglob('*') if p.is_file()
                  and p.suffix in extensions and '__pycache__' not in p.parts and p.name not in SKIP]
    for path in paths:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('missing or unsafe source: ' + str(path.relative_to(source)))
        cursor = path
        while cursor != source:
            if cursor.is_symlink() or (hasattr(cursor, 'is_junction') and cursor.is_junction()):
                raise ValueError('source contains a filesystem link')
            cursor = cursor.parent
        relative = path.relative_to(source).as_posix()
        if 'private' in path.name.lower() or path.name in {'settings.json', '.env'}:
            raise ValueError('private data is not publishable: ' + relative)
        if path.suffix == '.pem' and relative != 'assets/update-public-key.pem':
            raise ValueError('only the pinned public key may be exported')
        data = path.read_bytes()
        if SECRET.search(data) or PERSONAL.search(data):
            raise ValueError('potential secret or personal path: ' + relative)
    return sorted(set(paths))


def export(output, source=ROOT):
    source = Path(source).resolve()
    output = Path(output).absolute()
    if output.exists() or source.is_relative_to(output.resolve()):
        raise ValueError('choose a new export directory')
    paths = source_files(source)  # Validate everything before writing any output.
    manifest = []
    for path in paths:
        relative = path.relative_to(source)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        manifest.append(hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + relative.as_posix())
    (output / 'MANIFEST.sha256').write_text('\n'.join(manifest) + '\n', encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    export(parser.parse_args().output)
