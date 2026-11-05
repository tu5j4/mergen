"""Non-blocking, optional whole-system utilization sampling."""
import shutil
import csv
import io

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


def parse_gpu_usage(output: str) -> dict:
    # The command selects the runtime adapter; parse its single CSV row.
    # Unknown readings stay unknown instead of looking like zero-percent load.
    result = {'gpu': None, 'vram': None}
    lines = output.strip().splitlines()
    if not lines:
        return result
    fields = [v.strip() for v in lines[0].split(',')]
    if len(fields) != 3:
        return result
    try:
        result['gpu'] = max(0, min(100, round(float(fields[0]))))
    except (ValueError, OverflowError):
        pass
    try:
        used, total = float(fields[1]), float(fields[2])
        if total > 0:
            result['vram'] = max(0, min(100, round(100 * used / total)))
    except (ValueError, OverflowError):
        pass
    return result


def selected_gpu_row(output, uuid=None, name=None):
    """Map runtime identity to physical NVIDIA rows, never CUDA/SMI ordinals."""
    rows=[row for row in csv.reader(io.StringIO(output)) if len(row)==5]
    def identity(value):
        return str(value).strip().casefold().removeprefix('gpu-').replace('-','')
    if uuid:
        matches=[row for row in rows if identity(row[0])==identity(uuid)]
    elif name:
        matches=[row for row in rows if row[1].strip().casefold()==name.strip().casefold()]
    else:
        matches=rows if len(rows)==1 else []
    return matches[0] if len(matches)==1 else None

def selected_gpu_usage(output, uuid=None, name=None):
    row=selected_gpu_row(output,uuid,name)
    return parse_gpu_usage(','.join(row[2:])) if row is not None else {'gpu':None,'vram':None}


class UsageMonitor(QObject):
    readings = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = {'gpu': False, 'vram': False, 'cpu': False}
        self.command = shutil.which('nvidia-smi')
        self.native = None
        self.native_attempted = False
        self.backend = 'nvidia'
        self.device_index = 0
        self.adapter_name = None
        self.adapter_luid = None
        self.adapter_uuid = None
        self.source = 'nvidia-smi · tüm adaptör'
        try:
            import psutil
            self.cpu_percent = psutil.cpu_percent
            self.cpu_percent(interval=None)
        except ImportError:
            self.cpu_percent = None
        self._generation = 0
        self.process = self._new_process(self._generation)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.sample)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(2000)
        self.timeout.timeout.connect(lambda: self.process.kill())

    def _new_process(self, generation):
        process = QProcess(self)
        process.finished.connect(lambda code, status: self._finished(code, status, process, generation))
        process.errorOccurred.connect(lambda error: self._failed(error, process, generation))
        return process

    def set_runtime_adapter(self, backend, device_index=0, name=None, luid=None, uuid=None):
        """Select the runtime adapter. Readings cover all processes on that adapter."""
        selection=(backend,max(0,int(device_index)),name,luid,uuid)
        if selection==(self.backend,self.device_index,self.adapter_name,self.adapter_luid,self.adapter_uuid):
            return
        self.timeout.stop()
        previous = self.process
        self._generation += 1
        self.process = self._new_process(self._generation)
        if previous.state()!=QProcess.ProcessState.NotRunning:
            previous.finished.connect(previous.deleteLater)
            previous.kill()
        else:
            previous.deleteLater()
        if self.native is not None:
            self.native.close()
        self.native=None
        self.native_attempted=False
        self.backend,self.device_index,self.adapter_name,self.adapter_luid,self.adapter_uuid=selection
        self.source=('nvidia-smi' if backend=='nvidia' else 'windows')+' · tüm adaptör'
        self.readings.emit({'gpu':None,'vram':None})

    def set_enabled(self, gpu, vram, cpu):
        self.enabled = dict(gpu=gpu, vram=vram, cpu=cpu)
        if any(self.enabled.values()):
            self.timer.start()
            self.sample()
        else:
            self.timer.stop()
        if not (gpu or vram):
            self.timeout.stop()
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self.process.kill()

    def sample(self):
        if self.enabled['cpu']:
            value = self.cpu_percent(interval=None) if self.cpu_percent else None
            self.readings.emit({'cpu': round(value) if value is not None else None})
        if not (self.enabled['gpu'] or self.enabled['vram']):
            return
        if self.backend not in ('nvidia','amd','intel'):
            self.readings.emit({'gpu':None,'vram':None})
            return
        if self.native is not None:
            self.readings.emit(self.native.sample())
        elif not self.command or self.backend != 'nvidia':
            self._fallback()
        elif self.process.state() == QProcess.ProcessState.NotRunning:
            self.process.start(self.command, [
                '--query-gpu=uuid,name,utilization.gpu,memory.used,memory.total',
                '--format=csv,noheader,nounits'])
            self.timeout.start()

    def _finished(self, code, _status, process=None, generation=None):
        process = self.process if process is None else process
        if generation is not None and generation != self._generation:
            return
        self.timeout.stop()
        output = bytes(process.readAllStandardOutput()).decode('utf-8', errors='replace')
        process.readAllStandardError()
        if self.enabled['gpu'] or self.enabled['vram']:
            if code == 0 and selected_gpu_row(output,self.adapter_uuid,self.adapter_name) is None:
                self.readings.emit({'gpu':None,'vram':None})
                return
            values = selected_gpu_usage(output,uuid=self.adapter_uuid,name=self.adapter_name) if code == 0 else {'gpu': None, 'vram': None}
            if all(values[key] is not None for key in ('gpu', 'vram')):
                self.readings.emit(values)
            else:
                self._fallback()

    def _failed(self, _error, process=None, generation=None):
        if generation is not None and generation != self._generation:
            return
        self.timeout.stop()
        if self.enabled['gpu'] or self.enabled['vram']:
            self._fallback()

    def _fallback(self):
        if self.backend not in ('nvidia','amd','intel') or (self.device_index != 0 and not (self.adapter_name or self.adapter_luid)):
            self.readings.emit({'gpu':None,'vram':None})
            return
        if not self.native_attempted:
            self.native_attempted = True
            try:
                from .windows_gpu_usage import WindowsGPUUsage
                self.native = WindowsGPUUsage(self.backend,name=self.adapter_name,luid=self.adapter_luid)
                self.source = 'windows · tüm adaptör · ' + self.native.name.lower()
            except OSError:
                self.native = None
        self.readings.emit(self.native.sample() if self.native else {'gpu': None, 'vram': None})

    def close(self):
        self.set_enabled(False, False, False)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.waitForFinished(1000)
        if self.native is not None:
            self.native.close()
            self.native = None
