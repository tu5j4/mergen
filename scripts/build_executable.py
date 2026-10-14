"""Build only the UI; model packages remain in managed per-backend environments."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
# Poppler's ICU DLL has a colliding filename but incompatible exported names.
os.environ['PATH']=os.pathsep.join(p for p in os.environ.get('PATH','').split(os.pathsep) if 'poppler' not in p.lower())
# Reuse the existing build tool without altering the working app's environment.
base_site=Path(sys.base_prefix)/'Lib/site-packages'
if str(base_site) not in sys.path:sys.path.append(str(base_site))
import PyInstaller.__main__
# Paddle's oneDNN library needs the x64 Microsoft OpenMP runtime even on CPU.
# Fail the build rather than silently producing a package that only works on
# developer machines with the Visual C++ redistributable already installed.
openmp=Path(os.environ['SystemRoot'])/'System32/vcomp140.dll'
if not openmp.is_file():
    raise RuntimeError('Install the Microsoft Visual C++ x64 redistributable before building: vcomp140.dll is missing')
args=['--noconfirm','--clean','--windowed','--onedir','--name','Mergen','--icon',str(ROOT/'assets/mergen.ico'),
      '--paths',str(ROOT),'--hidden-import','PySide6.QtQuick','--hidden-import','PySide6.QtQuickControls2',
      '--hidden-import','cryptography.hazmat.primitives.asymmetric.ed25519',
      '--collect-data','certifi']
args+=['--add-binary',str(openmp)+os.pathsep+'.']
for name in ('torch','torchvision','paddle','paddleocr','paddlex','transformers','ctranslate2','huggingface_hub',
             'manga_ocr','scipy','pandas','matplotlib','IPython','notebook','pytest','tkinter'):
    args+=['--exclude-module',name]
from bundle_files import bundle_sources
sources=list(bundle_sources(ROOT))
for path in sources:
    args+=['--add-data',str(path)+os.pathsep+str(path.parent.relative_to(ROOT))]
# Python 3.12 workers must never import bundled Python 3.11 extension modules.
# Ship pure project sources under their own import root, separate from UI libraries.
for path in sources:
    if path.relative_to(ROOT).parts[0] in ('app','installer','scripts') and path.suffix in ('.py','.json'):
        args+=['--add-data',str(path)+os.pathsep+str(Path('runtime-source')/path.parent.relative_to(ROOT))]
for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
    args+=['--add-data',str(ROOT/name)+os.pathsep+'.']
args+=[str(ROOT/'main.py')]
PyInstaller.__main__.run(args)


# WebEngine is pulled in by broad Qt QML hooks but the UI uses no browser.
# Remove only named, unused payloads within this build's output.
import shutil
bundle=(ROOT/'dist/Mergen/_internal').resolve()
for relative in ('PySide6/qml/QtWebEngine','scripts/install_test_cpu.py','scripts/verify_local_models.py','scripts/diagnose_bundle.py','PySide6/QtWebEngineProcess.exe','QtWebEngineProcess.exe',
                 'Qt6WebEngineCore.dll','Qt6WebEngineQuick.dll','PySide6/Qt6WebEngineCore.dll','PySide6/Qt6WebEngineQuick.dll','PySide6/Qt6WebEngineQuickDelegatesQml.dll','PySide6/resources','PySide6/translations/qtwebengine_locales'):
    target=bundle/relative
    if not target.resolve().is_relative_to(bundle):raise ValueError('Unsafe bundle prune path')
    if target.is_dir():shutil.rmtree(target)
    elif target.is_file():target.unlink()


# Keep one matching VC runtime set: Qt's packaged runtime is redistributable
# and avoids mixing System32 and Python's older CRT DLLs in the frozen loader.
import PySide6
qt_dir=Path(PySide6.__file__).parent
for pattern in ('MSVCP140*.dll','VCRUNTIME140*.dll'):
    for dll in qt_dir.glob(pattern):shutil.copy2(dll,bundle/dll.name)
