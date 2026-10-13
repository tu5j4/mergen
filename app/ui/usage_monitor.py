"""Non-blocking, optional whole-system utilization sampling."""
import shutil

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


def parse_gpu_usage(output: str) -> dict:
    # Use GPU 0, matching the OCR/translation device. Unknown readings stay
    # unknown instead of looking like a genuine zero-percent load.
    result = {'gpu': None, 'vram': None}
    lines = output.strip().splitlines()
    if not lines:
        return result
    fields = [v.strip() for v in lines[0].split(',')]
    if len(fields) != 3:
        return result
    try:
        result['gpu'] = max(0, min(100, round(float(fields[0]))))
    except ValueError:
        pass
    try:
        used, total = float(fields[1]), float(fields[2])
        if total > 0:
            result['vram'] = max(0, min(100, round(100 * used / total)))
    except ValueError:
        pass
    return result


class UsageMonitor(QObject):
    readings = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = {'gpu': False, 'vram': False, 'cpu': False}
        self.command = shutil.which('nvidia-smi')
        self.native = None
        self.native_attempted = False
        self.source = 'nvidia-smi'
        try:
            import psutil
            self.cpu_percent = psutil.cpu_percent
            self.cpu_percent(interval=None)
        except ImportError:
            self.cpu_percent = None
        self.process = QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._failed)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.sample)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(2000)
        self.timeout.timeout.connect(self.process.kill)

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
        if self.native is not None:
            self.readings.emit(self.native.sample())
        elif not self.command:
            self._fallback()
        elif self.process.state() == QProcess.ProcessState.NotRunning:
            self.process.start(self.command, [
                '--id=0', '--query-gpu=utilization.gpu,memory.used,memory.total',
                '--format=csv,noheader,nounits'])
            self.timeout.start()

    def _finished(self, code, _status):
        self.timeout.stop()
        output = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.process.readAllStandardError()
        if self.enabled['gpu'] or self.enabled['vram']:
            values = parse_gpu_usage(output) if code == 0 else {'gpu': None, 'vram': None}
            if all(values[key] is not None for key in ('gpu', 'vram')):
                self.readings.emit(values)
            else:
                self._fallback()

    def _failed(self, _error):
        self.timeout.stop()
        if self.enabled['gpu'] or self.enabled['vram']:
            self._fallback()

    def _fallback(self):
        if not self.native_attempted:
            self.native_attempted = True
            try:
                from .windows_gpu_usage import WindowsGPUUsage
                self.native = WindowsGPUUsage()
                self.source = 'windows · ' + self.native.name
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
