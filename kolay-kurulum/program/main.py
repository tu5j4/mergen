"""
mergen — manga / manhwa / çizgi roman ekran çevirmeni
Giriş noktası.

Çalıştırma:  python main.py
"""
import os
import sys
from app.runtime_paths import configure_runtime
configure_runtime()

# Windows'ta torch'u Qt'den ÖNCE import etmek DLL çakışmalarını (WinError 1114 vb.) önler.
try:
    import torch  # noqa: F401
except Exception:
    pass

from app.gpu_env import setup_cuda_dll_paths
setup_cuda_dll_paths()

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from app.ui.control_panel import ControlPanel


def main() -> int:
    if sys.platform == 'win32':
        # Windows must know the taskbar identity before any window is created.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('mergen.desktop')
    # Ölçekleme oranlarını yuvarlamadan kullan (125%, 150% gibi ekranlarda doğru koordinat için)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("mergen")
    app.setApplicationDisplayName("mergen")
    from app.config import APP_ICON
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setQuitOnLastWindowClosed(True)

    panel = ControlPanel()
    panel.show()
    return app.exec()


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
