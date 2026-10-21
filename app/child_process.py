"""Start external Python without inheriting the frozen UI's DLL search path."""
import os
import subprocess
import sys
import threading
from pathlib import Path

_LAUNCH_LOCK=threading.Lock()

def external_environment(environment):
    result=dict(environment)
    result.pop('PYTHONHOME',None);result.pop('PYTHONPATH',None)
    result.update(PYTHONUTF8='1',PYTHONUNBUFFERED='1',PIP_NO_INPUT='1')
    if getattr(sys,'frozen',False):
        home=Path(sys._MEIPASS).resolve()
        result['PATH']=os.pathsep.join(part for part in result.get('PATH','').split(os.pathsep)
            if part and not Path(part).resolve().is_relative_to(home))
    return result

def popen_external(args,**kwargs):
    from app.operations import check_cancelled, own_process
    check_cancelled()
    kwargs['env']=external_environment(kwargs.get('env',os.environ))
    if os.name!='nt' or not getattr(sys,'frozen',False):return own_process(subprocess.Popen(args,**kwargs))
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetDllDirectoryW.argtypes=[ctypes.c_uint32,ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
    kernel.SetErrorMode.argtypes=[ctypes.c_uint32]
    with _LAUNCH_LOCK:
        buffer=ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(buffer),buffer)
        previous=buffer.value
        kernel.SetDllDirectoryW(None)
        error_mode=kernel.SetErrorMode(0x0001|0x0002|0x8000)
        try:return own_process(subprocess.Popen(args,**kwargs))
        finally:
            kernel.SetErrorMode(error_mode)
            kernel.SetDllDirectoryW(previous or None)
