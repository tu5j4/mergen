"""Read-only hardware discovery. Eligibility is followed by runtime tests."""
import csv
import ctypes
import io
import json
import platform
import shutil
import struct
import subprocess
import sys


def capture(command):
    try:
        return subprocess.check_output(command, text=True, encoding='utf-8', errors='replace',
            timeout=20, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def vendor(name):
    name = name.lower()
    if 'nvidia' in name:
        return 'nvidia'
    if 'amd' in name or 'radeon' in name or 'advanced micro' in name:
        return 'amd'
    if 'intel' in name:
        return 'intel'
    return 'bilinmiyor'


def cuda_eligible(gpu):
    try:
        driver = tuple(int(n) for n in gpu['driver'].split('.')[:2])
        capability = float(gpu['compute_capability'])
        return driver >= (576, 2) and 7.5 <= capability <= 12.0
    except (KeyError, ValueError, TypeError):
        return False


def detect():
    windows = sys.platform == 'win32'
    report = {'os': platform.system(), 'machine': platform.machine(),
              'python': platform.python_version(), 'bits': struct.calcsize('P') * 8,
              'adapters': [], 'nvidia': [], 'avx': None, 'vc_runtime': False}
    if windows:
        raw = capture(['powershell.exe', '-NoProfile', '-Command',
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
            "@(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) | ConvertTo-Json -Compress"])
        try:
            names = json.loads(raw)
            names = [names] if isinstance(names, str) else names or []
            report['adapters'] = [{'name': n, 'vendor': vendor(n)} for n in names]
        except ValueError:
            pass
        report['avx'] = bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(39))
        try:
            ctypes.WinDLL('vcruntime140.dll')
            ctypes.WinDLL('msvcp140.dll')
            report['vc_runtime'] = True
        except OSError:
            pass
    smi = shutil.which('nvidia-smi')
    if smi:
        raw = capture([smi, '--query-gpu=index,name,driver_version,memory.total,compute_cap',
                       '--format=csv,noheader,nounits'])
        for row in csv.reader(io.StringIO(raw)):
            if len(row) == 5:
                index, name, driver, memory, capability = (x.strip() for x in row)
                report['nvidia'].append(dict(index=index, name=name, driver=driver,
                                             memory_mib=memory, compute_capability=capability))
    report['supported_os'] = windows and platform.machine().lower() in ('amd64', 'x86_64') and report['bits'] == 64 and sys.getwindowsversion().build >= 19041
    report['supported_python'] = sys.version_info[:2] == (3, 11)
    # The application uses CUDA device 0; don't approve a different GPU silently.
    first = next((g for g in report['nvidia'] if g['index'] == '0'), {})
    report['cuda_candidate'] = cuda_eligible(first)
    report['free_gib'] = round(shutil.disk_usage(__file__).free / 1024**3, 1)
    return report
