"""Export the current installer source without local data or private keys."""
import argparse,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
TREES={'app':{'.py','.qml','.json'},'assets':{'.png','.ico','.svg','.pem'},
       'installer':{'.py','.iss','.ps1','.txt'},'scripts':{'.py','.ps1'},
       'tests':{'.py'},'docs':{'.md'},'.github':{'.yml','.yaml'}}
FILES=('main.py','next_main.py','baslat.bat','baslat-yeni.bat','kurulum.bat',
       'bagliliklar.bat','requirements.txt','requirements-dev.txt','README.md',
       'LICENSE','THIRD_PARTY_NOTICES.md','.gitignore','.gitattributes')
def source_files(source=ROOT):
    source=Path(source).resolve()
    paths=[source/name for name in FILES]
    for folder,extensions in TREES.items():
        paths += [p for p in (source/folder).rglob('*') if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts]
    result=[]
    for path in sorted(paths):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(source) or 'private' in path.name.lower():
            raise ValueError('Güvensiz veya eksik kaynak: '+str(path))
        if path.name in ('install_test_cpu.py','verify_local_models.py','diagnose_bundle.py','publish_local_copy.ps1'):continue
        result.append(path)
    return result

def export(output,source=ROOT):
    source=Path(source).resolve();output=Path(output).absolute()
    if output.is_symlink() or source.is_relative_to(output.resolve()):raise ValueError('Güvensiz hedef klasör')
    if output.exists():raise FileExistsError('Yeni bir hedef klasör seçin')
    paths=source_files(source)
    manifest=[]
    for path in paths:
        relative=path.relative_to(source)
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        manifest.append(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+relative.as_posix())
    (output/'MANIFEST.sha256').write_text('\n'.join(manifest)+'\n',encoding='utf-8')
    return output
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);export(parser.parse_args().output)
