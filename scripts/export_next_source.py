"""Export only the new version's source; never include runtimes, models or keys."""
import argparse,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
TREES={'app':{'.py','.qml','.json'},'assets':{'.png','.ico','.svg','.pem'},
       'installer':{'.py','.iss','.ps1'},'scripts':{'.py','.ps1'},'tests':{'.py'},'docs':{'.md'}}
FILES=('next_main.py','baslat-yeni.bat','README.md','LICENSE','THIRD_PARTY_NOTICES.md','.gitignore')
def export(output):
    output=output.absolute()
    if output.exists() or ROOT.is_relative_to(output.resolve()):raise ValueError('Yeni bir hedef klasör seçin')
    paths=[ROOT/name for name in FILES]
    for folder,extensions in TREES.items():
        paths += [p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts]
    manifest=[]
    for source in sorted(paths):
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT) or 'private' in source.name.lower():raise ValueError('Güvensiz kaynak')
        relative=source.relative_to(ROOT)
        if source.name in ('install_test_cpu.py','verify_local_models.py','diagnose_bundle.py','publish_local_copy.ps1'):continue
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        manifest.append(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+relative.as_posix())
    (output/'MANIFEST.sha256').write_text('\n'.join(manifest)+'\n',encoding='utf-8')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);export(parser.parse_args().output)
