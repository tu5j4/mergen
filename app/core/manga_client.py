"""Bounded persistent subprocess client; keeps Torch CUDA outside Paddle."""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from ..config import PROJECT_ROOT


def isolated_python() -> Path:
    return PROJECT_ROOT / '.manga-venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def worker_environment():
    env = dict(os.environ)
    # Parent has Paddle/nvidia CUDA 12.9 DLL paths. The helper must use only
    # its own Torch CUDA runtime, even when launched after Paddle was loaded.
    env['PATH'] = os.pathsep.join(p for p in env.get('PATH', '').split(os.pathsep)
        if not any(s in p.lower().replace('\\', '/') for s in
                   ('/site-packages/', '/.venv/', '/.manga-venv/')))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    env['PYTHONUTF8'] = '1'
    env['HF_HUB_OFFLINE'] = '1'
    env['TRANSFORMERS_OFFLINE'] = '1'
    return env


class MangaClient:
    def __init__(self, device='auto', timeout=120):
        self._process = None
        self._responses = queue.Queue()
        self.timeout = timeout
        self.device = 'cpu'
        self.stats = {}
        self._lock = threading.Lock()
        helper = isolated_python()
        if device == 'cuda' and not helper.exists():
            raise RuntimeError('İzole manga GPU ortamı yok. bagliliklar.bat içinden manga-ocr gpu bileşenini kurun.')
        # CPU fallback also lives in a subprocess, not in Paddle's runtime.
        python = str(helper) if helper.exists() else sys.executable
        requested = device if helper.exists() else 'cpu'
        try:
            self._process = subprocess.Popen(
                [python, '-u', str(PROJECT_ROOT/'scripts/manga_worker.py'), '--device', requested],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', env=worker_environment(), cwd=PROJECT_ROOT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._reader = threading.Thread(target=self._read, args=(self._process.stdout,), daemon=True)
            self._reader.start()
            ready = self._receive()
            self.device = ready['device']
            self.pid = ready['pid']
        except Exception:
            self.close()
            raise

    def _read(self, stdout):
        try:
            for line in stdout:
                try:
                    self._responses.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            stdout.close()
            self._responses.put({'ok': False, 'error': 'manga-ocr yardımcı işlemi kapandı.'})

    def _receive(self):
        try:
            value = self._responses.get(timeout=self.timeout)
        except queue.Empty:
            self.close()
            raise TimeoutError('manga-ocr yanıt süresi aşıldı.')
        if not value.get('ok'):
            raise RuntimeError(value.get('error', 'manga-ocr hatası'))
        self.stats = value.get('stats', self.stats)
        return value

    def _request(self, data):
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                raise RuntimeError('manga-ocr yardımcı işlemi çalışmıyor.')
            self._process.stdin.write(json.dumps(data)+'\n')
            self._process.stdin.flush()
            return self._receive()

    def recognize(self, crops):
        if not crops:
            return []
        if len(crops) > 4:
            raise ValueError('manga-ocr batch en fazla 4 olabilir.')
        encoded = []
        for crop in crops:
            buffer = io.BytesIO()
            crop.convert('RGB').save(buffer, format='PNG')
            encoded.append(base64.b64encode(buffer.getvalue()).decode('ascii'))
        texts = self._request({'op': 'recognize', 'images': encoded})['texts']
        if len(texts) != len(crops):
            raise RuntimeError('manga-ocr sonuç sayısı kırpım sayısıyla eşleşmiyor.')
        return texts

    def memory_stats(self):
        return self._request({'op': 'stats'})['stats']

    def close(self):
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=3)
        except Exception:
            process.kill()
            process.wait(timeout=3)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
