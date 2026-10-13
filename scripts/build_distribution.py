"""Export an explicit source allowlist; never bundle local environments or models."""
from pathlib import Path
import argparse
import hashlib
import shutil

ROOT = Path(__file__).resolve().parent.parent
FILES = ('main.py', 'requirements.txt', 'kurulum.bat', 'baslat.bat',
         'bagliliklar.bat', 'README.md', 'docs/kurulum.md', 'LICENSE',
         'THIRD_PARTY_NOTICES.md', '.gitignore', '.gitattributes',
         'assets/mergen-logo.png', 'assets/mergen.ico',
         'app/data/translation_glossary.json',
         'app/data/session_terms.json', 'scripts/manga_worker.py',
         'scripts/setup_manga_gpu.py', 'scripts/download_models.py',
         'scripts/build_icon.py',
         'scripts/build_distribution.py')
TREES = {'app': {'.py'}, 'installer': {'.py', '.ps1', '.txt'},
         'tests': {'.py'}, '.github': {'.yml'}}


def source_files(source):
    paths = [source / name for name in FILES]
    for folder, extensions in TREES.items():
        paths.extend(p for p in (source / folder).rglob('*')
                     if p.is_file() and p.suffix in extensions
                     and '__pycache__' not in p.parts)
    for path in paths:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(f'missing or unsafe source: {path}')
    return sorted(paths)


def build(output, source=ROOT):
    source = Path(source).resolve()
    output = Path(output).absolute()
    if output.is_symlink() or output.resolve() == source or source.is_relative_to(output.resolve()):
        raise ValueError('unsafe output directory')
    if output.exists():
        raise FileExistsError('output already exists; use a new directory to preserve existing files')
    paths = source_files(source)
    output.mkdir(parents=True)
    for destination in (output / 'kolay-kurulum', output / 'github'):
        destination.mkdir(exist_ok=True)
        manifest = []
        for path in paths:
            relative = path.relative_to(source)
            if destination.name == 'kolay-kurulum':
                if relative.parts[0] in ('tests', '.github', 'docs') or relative.as_posix() in (
                        'README.md', 'requirements.txt', '.gitignore', '.gitattributes',
                        'scripts/build_distribution.py'):
                    continue
                if relative.as_posix() in ('kurulum.bat', 'baslat.bat', 'bagliliklar.bat'):
                    target = destination / relative
                    content = path.read_text(encoding='utf-8').replace('%~dp0', '%~dp0program\\')
                    target.write_bytes(content.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
                    continue
                relative = Path('program') / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            manifest.append(f'{hashlib.sha256(target.read_bytes()).hexdigest()}  {relative.as_posix()}')
        if destination.name == 'kolay-kurulum':
            (destination / 'beni-oku.txt').write_text(
                'mergen\n\n1. ilk kez kullanacaksan kurulum.bat dosyasini ac.\n'
                '2. kurulum tamamlaninca baslat.bat ile uygulamayi ac.\n'
                '3. daha sonra model kurmak/kaldirmak icin bagliliklar.bat dosyasini ac.\n\n'
                'ilk kurulum internet gerektirir. secimlerin onaylanmadan model kurulmaz.\n'
                'uygulama windows uzerinde dogrudan calisir; docker veya sandbox gerekmez.\n'
                'paylasmak icin kurulmamis kolay-kurulum klasorunun tamamini zip yapin.\n'
                'program klasoru uygulamanin ic dosyalaridir; tasirken tum klasoru birlikte tasi.\n'
                'bu paket windows x64 ve python 3.11 icindir; python yoksa kurulum yardim eder.\n'
                'nvidia desteklenirse gpu, amd/intel icin cpu kullanilir.\n'
                'kod ve model lisanslari program/LICENSE ve program/THIRD_PARTY_NOTICES.md icindedir.\n',
                encoding='utf-8')
        else:
            (destination / 'MANIFEST.sha256').write_text('\n'.join(manifest) + '\n', encoding='utf-8')
    print(f'User package and developer source exported: {output}')
    print('No environments, settings, model weights, screenshots or logs included.')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
