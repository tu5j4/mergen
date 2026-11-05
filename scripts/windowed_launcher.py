"""Use PyInstaller's documented external PKG layout with a stock GUI loader.

Keep PE resources untouched. The normal asInvoker/Common-Controls manifest is
external, and the only appended bytes are PyInstaller's official PKG marker.
Application version and icon come from the application UI and installer.
"""
import hashlib
import os
from pathlib import Path
import shutil

PKG_MARKER = b'MEI\015\013\012\013\016'


def prepare(root):
    import PyInstaller
    from PyInstaller.utils.win32.winmanifest import create_application_manifest
    root=Path(root).resolve()
    bundle=root/'dist/Mergen'
    package=root/'build/Mergen/Mergen.pkg'
    stock=Path(PyInstaller.__file__).parent/'bootloader'/PyInstaller.PLATFORM/'runw.exe'
    if not package.is_file() or not stock.is_file() or not bundle.is_dir():
        raise ValueError('built PKG, stock windowed bootloader and bundle are required')
    executable=bundle/'Mergen.exe'
    manifest=bundle/'Mergen.exe.manifest'
    # Write the sidecar before replacing the loader. A fresh executable mtime
    # invalidates Windows activation-context caching for this application path.
    manifest.write_bytes(create_application_manifest())
    shutil.copy2(package,bundle/'Mergen.pkg')
    temporary=bundle/'Mergen-launcher.tmp'
    temporary.write_bytes(stock.read_bytes()+PKG_MARKER)
    os.replace(temporary,executable)
    os.utime(executable,None)
    return dict(layout='stock-windowed-external-pkg',
                executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                stock_sha256=hashlib.sha256(stock.read_bytes()).hexdigest(),
                pkg_sha256=hashlib.sha256(package.read_bytes()).hexdigest(),
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                pe_resources='unmodified stock loader; app version is reported by UI/installer')
