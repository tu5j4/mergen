"""
Windows'ta CTranslate2'nin CUDA DLL'lerini (cublas64_12.dll, cudnn64_9.dll) bulabilmesi için
torch ve nvidia-* paketlerinin DLL klasörlerini PATH'e ekler.
(CTranslate2 DLL'leri kendi içinden LoadLibrary ile yükler; os.add_dll_directory yetmez.)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def setup_cuda_dll_paths() -> None:
    if sys.platform != "win32":
        return
    dirs: list[Path] = []
    try:
        import torch
        dirs.append(Path(torch.__file__).parent / "lib")
    except Exception:
        pass
    try:
        import nvidia  # nvidia-cublas-cu12 vb. kuruluysa
        for base in list(nvidia.__path__):
            dirs += list(Path(base).glob("*/bin"))
    except Exception:
        pass

    existing = os.environ.get("PATH", "")
    add = [str(d) for d in dirs if d.is_dir() and str(d) not in existing]
    if add:
        os.environ["PATH"] = os.pathsep.join(add + [existing])
    for d in add:
        try:
            os.add_dll_directory(d)
        except Exception:
            pass
