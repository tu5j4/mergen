"""Bounded JSON-lines RPC to isolated, application-owned ML environments."""
import base64
import io
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from ..child_process import popen_external
from ..operations import check_cancelled, Cancelled
from ..storage import APP_ROOT, WORKER_ROOT, DATA_ROOT, cache_environment


def environment_key(backend, task):
    if backend == 'nvidia' and task == 'ocr':
        return 'nvidia-paddle'
    return backend


class RuntimeClient:
    def __init__(self, task, backend, language='en', model='', timeout=180, canvas=1600,
                 startup_timeout=300, progress=None):
        if task not in ('translate', 'ocr', 'manga') or backend not in ('cpu','nvidia','amd','intel'):
            raise ValueError('Geçersiz çalışma ortamı')
        self.task, self.timeout = task, timeout
        self._progress = progress
        self._log_stream = None
        self._phase = 'model hazırlanıyor'
        self._responses, self._lock = queue.Queue(), threading.Lock()
        self._process = None
        python = DATA_ROOT / 'envs' / environment_key(backend, task) / 'Scripts/python.exe'
        if not python.is_file():
            raise RuntimeError('Önce bileşenler ekranından çalışma ortamını kurun: ' + environment_key(backend, task))
        env = cache_environment()
        env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', MERGEN_DATA_DIR=str(DATA_ROOT),
                   PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True')
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        env['PATH'] = os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep)
            if 'site-packages' not in p.lower() and '.venv' not in p.lower())
        try:
            logs=DATA_ROOT/'logs';logs.mkdir(parents=True,exist_ok=True)
            self._log_path=logs/f'runtime-{task}-{backend}-stderr.log'
            self._log_stream=self._log_path.open('a',encoding='utf-8')
            self._process = popen_external([str(python), '-u', str(WORKER_ROOT/'scripts/runtime_worker.py'),
                '--task',task,'--backend',backend,'--canvas',str(max(1280,min(2560,int(canvas)))),'--language',language,'--model',str(model)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log_stream,
                text=True, encoding='utf-8', env=env, cwd=WORKER_ROOT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            threading.Thread(target=self._read,args=(self._process,),daemon=True).start()
            ready = self._receive(timeout=startup_timeout)
            self.device = ready['device']
        except Exception:
            self.close()
            raise

    def _read(self,process):
        for line in process.stdout:
            try:
                parsed=json.loads(line)
                if isinstance(parsed,dict) and ('ok' in parsed or parsed.get('event')=='progress'):
                    self._responses.put(parsed)
            except ValueError:
                pass
        self._responses.put({'ok':False,'error':'Model işlemi kapandı.'})

    def _receive(self, timeout=None):
        deadline=time.monotonic()+(self.timeout if timeout is None else timeout)
        while True:
            check_cancelled()
            try:
                response=self._responses.get(timeout=max(0,min(.1,deadline-time.monotonic())))
            except queue.Empty:
                if time.monotonic()<deadline:continue
                name=getattr(self,'_log_path',Path('runtime.log')).name
                raise TimeoutError('model yanıtı gecikti · '+getattr(self,'_phase','model hazırlanıyor')+' · günlük: '+name)
            if response.get('event')!='progress':break
            self._phase=str(response.get('phase','model hazırlanıyor'))[:160]
            if self._progress:self._progress(self._phase)
        if not response.get('ok'):
            raise RuntimeError(response.get('error','Model işlemi başarısız.'))
        return response

    def request(self, **payload):
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                raise RuntimeError('Model işlemi çalışmıyor.')
            self._phase='ocr metni okunuyor' if self.task=='ocr' else 'model isteği işleniyor'
            self._process.stdin.write(json.dumps(payload,ensure_ascii=True)+'\n')
            self._process.stdin.flush()
            try:return self._receive()['result']
            except (TimeoutError, Cancelled):
                self.close();raise

    @staticmethod
    def encode_image(image):
        from PIL import Image
        if not isinstance(image, Image.Image):
            image = Image.fromarray(image)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('ascii')

    def predict(self, rgb):
        yield self.request(op='ocr', image=self.encode_image(rgb))

    def recognize(self, crops):
        if len(crops)>4:
            raise ValueError('En fazla dört manga kırpımı gönderilebilir.')
        return self.request(op='manga', images=[self.encode_image(i) for i in crops])

    def close(self):
        process, self._process = self._process, None
        try:
            if process is not None:
                try:
                    process.stdin.write('{"op":"close"}\n'); process.stdin.flush()
                    process.wait(timeout=5)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    # Windows venv launchers own a second Python process.
                    import psutil
                    try:
                        for child in reversed(psutil.Process(process.pid).children(recursive=True)):
                            try:child.kill()
                            except psutil.Error:pass
                    except psutil.Error:pass
                    if process.poll() is None:process.kill()
                    process.wait(timeout=5)
        finally:
            if self._log_stream is not None:
                self._log_stream.close();self._log_stream=None
