"""Restore pixels behind our shared overlay without changing its visibility.

Only covered rectangles are reconstructed. Everything else comes from the
normal screen capture, preserving the visible desktop and window ordering.
"""
import ctypes
from ctypes import wintypes as W
import threading

import numpy as np


class WindowsUnderlayCapture:
    def __init__(self):
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.gdi=ctypes.WinDLL('gdi32',use_last_error=True)
        self.dwm=ctypes.WinDLL('dwmapi',use_last_error=True)
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self._pending=None
        self.callback=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        definitions=[
            (self.user,'EnumWindows',[self.callback,W.LPARAM],W.BOOL),
            (self.user,'IsWindowVisible',[W.HWND],W.BOOL),
            (self.user,'IsIconic',[W.HWND],W.BOOL),
            (self.user,'IsHungAppWindow',[W.HWND],W.BOOL),
            (self.user,'GetWindowRect',[W.HWND,ctypes.POINTER(W.RECT)],W.BOOL),
            (self.user,'GetWindowLongW',[W.HWND,ctypes.c_int],W.LONG),
            (self.user,'GetWindowThreadProcessId',[W.HWND,ctypes.POINTER(W.DWORD)],W.DWORD),
            (self.kernel,'GetCurrentThreadId',[],W.DWORD),
            (self.user,'GetDC',[W.HWND],W.HDC),
            (self.user,'ReleaseDC',[W.HWND,W.HDC],ctypes.c_int),
            (self.user,'PrintWindow',[W.HWND,W.HDC,W.UINT],W.BOOL),
            (self.gdi,'CreateCompatibleDC',[W.HDC],W.HDC),
            (self.gdi,'CreateDIBSection',[W.HDC,ctypes.c_void_p,W.UINT,ctypes.POINTER(ctypes.c_void_p),W.HANDLE,W.DWORD],W.HBITMAP),
            (self.gdi,'SelectObject',[W.HDC,W.HANDLE],W.HANDLE),
            (self.gdi,'DeleteObject',[W.HANDLE],W.BOOL),
            (self.gdi,'DeleteDC',[W.HDC],W.BOOL),
            (self.dwm,'DwmGetWindowAttribute',[W.HWND,W.DWORD,ctypes.c_void_p,W.DWORD],ctypes.c_long),
        ]
        for library,name,args,result in definitions:
            function=getattr(library,name);function.argtypes=args;function.restype=result

    def _rect(self,hwnd):
        rect=W.RECT()
        if not self.user.GetWindowRect(hwnd,ctypes.byref(rect)):return None
        return rect.left,rect.top,rect.right,rect.bottom

    def _render(self,hwnd,rect):
        # PrintWindow is synchronous and another application can stop handling
        # messages at any moment. Allow at most one outstanding render; a hung
        # window must not stall translation or create an unbounded thread pool.
        if self.user.GetWindowThreadProcessId(hwnd,None)==self.kernel.GetCurrentThreadId():
            return self._render_sync(hwnd,rect)
        if self._pending and not self._pending[0].is_set():return None
        ready=threading.Event();output=[]
        self._pending=(ready,output)
        def render():
            try:output.append(self._render_sync(hwnd,rect))
            except (OSError,ValueError):output.append(None)
            finally:ready.set()
        threading.Thread(target=render,daemon=True,name='window-capture').start()
        if not ready.wait(.15):return None
        self._pending=None
        return output[0] if output else None

    def _render_sync(self,hwnd,rect):
        width,height=rect[2]-rect[0],rect[3]-rect[1]
        if width<=0 or height<=0 or width*height>32_000_000:return None
        if self.user.IsHungAppWindow(hwnd):return None
        # Layered third-party windows require alpha composition; let the
        # existing clean-capture fallback handle those rather than guessing.
        if self.user.GetWindowLongW(hwnd,-20)&0x80000:return None
        class Header(ctypes.Structure):
            _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),
                ('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),
                ('image_size',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),
                ('used',W.DWORD),('important',W.DWORD)]
        header=Header(ctypes.sizeof(Header),width,-height,1,32,0,0,0,0,0,0)
        screen=self.user.GetDC(None);dc=bitmap=previous=None
        try:
            dc=self.gdi.CreateCompatibleDC(screen)
            pixels=ctypes.c_void_p()
            bitmap=self.gdi.CreateDIBSection(screen,ctypes.byref(header),0,ctypes.byref(pixels),None,0)
            if not dc or not bitmap or not pixels.value:return None
            previous=self.gdi.SelectObject(dc,bitmap)
            buffer=(ctypes.c_ubyte*(width*height*4)).from_address(pixels.value)
            image=np.ctypeslib.as_array(buffer).reshape(height,width,4)
            image[:]=(13,47,91,193)
            if not self.user.PrintWindow(hwnd,dc,2):return None  # PW_RENDERFULLCONTENT
            if np.all(image==(13,47,91,193)):return None
            return image[:,:,:3][:,:,::-1].copy()
        finally:
            if previous:self.gdi.SelectObject(dc,previous)
            if bitmap:self.gdi.DeleteObject(bitmap)
            if dc:self.gdi.DeleteDC(dc)
            if screen:self.user.ReleaseDC(None,screen)

    def restore(self,image,left,top,overlay_hwnd,areas):
        height,width=image.shape[:2]
        missing=np.zeros((height,width),dtype=bool)
        for x,y,w,h in areas:
            x0,y0=max(0,int(np.floor(x))),max(0,int(np.floor(y)))
            x1,y1=min(width,int(np.ceil(x+w))),min(height,int(np.ceil(y+h)))
            if x1>x0 and y1>y0:missing[y0:y1,x0:x1]=True
        if not missing.any():return image
        windows=[]
        @self.callback
        def collect(hwnd,param):
            windows.append(int(hwnd));return True
        if not self.user.EnumWindows(collect,0):return None
        result=image.copy();behind=False
        for hwnd in windows:
            if hwnd==overlay_hwnd:
                behind=True;continue
            if not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd):continue
            cloaked=W.DWORD()
            self.dwm.DwmGetWindowAttribute(hwnd,14,ctypes.byref(cloaked),ctypes.sizeof(cloaked))
            if cloaked.value:continue
            rect=self._rect(hwnd)
            if rect is None:continue
            l,t,r,b=rect
            # Invisible resize borders are not opaque desktop pixels.
            visible=W.RECT()
            if self.dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(visible),ctypes.sizeof(visible))==0:
                vl,vt,vr,vb=visible.left,visible.top,visible.right,visible.bottom
            else:vl,vt,vr,vb=rect
            x0,y0=max(0,vl-left,l-left),max(0,vt-top,t-top)
            x1,y1=min(width,vr-left,r-left),min(height,vb-top,b-top)
            if x1<=x0 or y1<=y0:continue
            part=missing[y0:y1,x0:x1]
            if not part.any():continue
            if not behind:
                # A window above our overlay is already correct in the frame.
                part[:]=False;continue
            rendered=self._render(hwnd,rect)
            if rendered is None:return None
            patch=rendered[top+y0-t:top+y1-t,left+x0-l:left+x1-l]
            if not patch[part].any():return None  # unsupported all-black GPU surface
            result[y0:y1,x0:x1][part]=patch[part]
            part[:]=False
            if not missing.any():return result
        return result if behind and not missing.any() else None
