"""Only ship files needed by the desktop UI and model workers."""
from pathlib import Path

WORKERS=('runtime_worker.py','component_models.py','manga_worker.py',
         'download_models.py','setup_manga_gpu.py')

def bundle_sources(root):
    root=Path(root).resolve()
    paths=[]
    for folder,suffixes in {'app':{'.py','.qml','.json'},
                           'assets':{'.png','.ico','.svg','.pem','.json'},
                           'installer':{'.py','.json','.txt'}}.items():
        paths.extend(p for p in (root/folder).rglob('*')
                     if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    paths += [root/'installer/apply-update.ps1']
    paths += [root/'scripts'/name for name in WORKERS]
    for path in sorted(paths):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Missing or unsafe bundle source: '+str(path))
        if 'private' in path.name.lower():raise ValueError('Private key must not be bundled')
        yield path
