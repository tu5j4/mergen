"""
Platforma özel yardımcılar.
En önemli kısım: overlay penceresini ekran yakalamadan HARİÇ tutmak.
Böylece uygulama kendi çevirisini tekrar OCR'lamaz ve titreme olmaz.
  - Windows 10 (2004+) / 11 : SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
  - macOS                   : NSWindow.sharingType = NSWindowSharingNone
  - Linux (X11)             : desteklenmiyor -> yakalama anında overlay kısa süre gizlenir
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

WDA_EXCLUDEFROMCAPTURE = 0x00000011


def exclude_from_capture(widget) -> bool:
    try:
        wid = int(widget.winId())
    except Exception:
        return False

    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
            return bool(user32.SetWindowDisplayAffinity(ctypes.c_void_p(wid), WDA_EXCLUDEFROMCAPTURE))
        except Exception as e:
            print(f"[platform] SetWindowDisplayAffinity başarısız: {e}")
            return False

    if sys.platform == "darwin":
        try:
            import objc  # pyobjc
            view = objc.objc_object(c_void_p=wid)
            window = view.window()
            if window is None:
                return False
            window.setSharingType_(0)  # NSWindowSharingNone
            return True
        except Exception as e:
            print(f"[platform] macOS sharingType ayarlanamadı: {e}")
            return False

    return False


def logical_to_capture_rect(rect: QRect) -> tuple[int, int, int, int]:
    """Qt mantıksal (DPI ölçekli) koordinatını mss'in beklediği koordinata çevirir."""
    if sys.platform == "darwin":
        # macOS'ta mss 'point' koordinatı ister, retina piksel döndürür
        return rect.x(), rect.y(), rect.width(), rect.height()

    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio()
    sg = screen.geometry()
    x = sg.x() + round((rect.x() - sg.x()) * dpr)
    y = sg.y() + round((rect.y() - sg.y()) * dpr)
    return x, y, round(rect.width() * dpr), round(rect.height() * dpr)
