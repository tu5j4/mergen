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
from .core.capture_geometry import ScreenDescriptor, build_capture_plan

WDA_EXCLUDEFROMCAPTURE = 0x00000011


def exclude_from_capture(widget, excluded: bool = True) -> bool:
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
            return bool(user32.SetWindowDisplayAffinity(ctypes.c_void_p(wid), WDA_EXCLUDEFROMCAPTURE if excluded else 0))
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
            window.setSharingType_(0 if excluded else 1)
            return True
        except Exception as e:
            print(f"[platform] macOS sharingType ayarlanamadı: {e}")
            return False

    return False


def _windows_screen_rects():
    """Read physical monitor origins under a temporary per-monitor thread DPI context."""
    import ctypes
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    class MonitorInfo(ctypes.Structure):
        _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),
                  ('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD),('szDevice',wintypes.WCHAR*32)]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
    user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
    user.GetMonitorInfoW.restype=wintypes.BOOL
    user.EnumDisplayMonitors.argtypes=[wintypes.HDC,ctypes.POINTER(wintypes.RECT),callback_type,wintypes.LPARAM]
    user.EnumDisplayMonitors.restype=wintypes.BOOL
    change=getattr(user,'SetThreadDpiAwarenessContext',None);previous=None
    if change is not None:
        change.argtypes=[ctypes.c_void_p];change.restype=ctypes.c_void_p
        previous=change(ctypes.c_void_p(-4))
    monitors={}
    @callback_type
    def visit(handle,dc,rect,data):
        info=MonitorInfo();info.cbSize=ctypes.sizeof(info)
        if user.GetMonitorInfoW(handle,ctypes.byref(info)):
            r=info.rcMonitor
            monitors[info.szDevice.casefold()]=(r.left,r.top,r.right-r.left,r.bottom-r.top)
        return True
    try:
        if not user.EnumDisplayMonitors(None,None,visit,0):raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if previous:change(previous)
    return monitors


def _windows_display_names():
    from .core.windows_display_config import windows_display_names
    return windows_display_names()


def screen_descriptors():
    """Snapshot Qt logical geometry and independently discovered physical origins."""
    screens=QGuiApplication.screens()
    native=_windows_screen_rects() if sys.platform=='win32' else {}
    aliases=_windows_display_names() if sys.platform=='win32' else {}
    descriptors=[]
    for screen in screens:
        geometry=screen.geometry();logical=(geometry.x(),geometry.y(),geometry.width(),geometry.height())
        name=screen.name();physical=native.get(name.casefold())
        if physical is None:
            physical=native.get(aliases.get(name.strip().casefold()))
        if physical is None and len(screens)==1 and len(native)==1:
            physical=next(iter(native.values()))
        if physical is None and sys.platform=='win32':
            raise RuntimeError('ekranın fiziksel başlangıcı bulunamadı; ekran düzenini yeniden seçin')
        origin=physical[:2] if physical else logical[:2]
        size=physical[2:] if physical else None
        descriptors.append(ScreenDescriptor(logical,origin,float(screen.devicePixelRatio()),name,size))
    return descriptors


def logical_capture_plan(rect: QRect):
    """Physical-coordinate capture plan; macOS point-based MSS keeps its legacy path."""
    if sys.platform=='darwin':raise ValueError('macos nokta koordinatı için eski tek ekran yakalama yolu kullanılmalı')
    return build_capture_plan((rect.x(),rect.y(),rect.width(),rect.height()),screen_descriptors())


def logical_to_capture_rect(rect: QRect) -> tuple[int,int,int,int]:
    """Compatibility rectangle for one screen; mixed screens require the piece plan."""
    if sys.platform=='darwin':
        return rect.x(),rect.y(),rect.width(),rect.height()
    return logical_capture_plan(rect).physical_bounds
