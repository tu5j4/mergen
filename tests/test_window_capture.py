import threading
import time
import unittest
from unittest.mock import Mock
from app.core.window_capture import WindowsUnderlayCapture


class WindowCaptureTests(unittest.TestCase):
    def test_hung_window_does_not_block_or_accumulate_render_threads(self):
        capture=object.__new__(WindowsUnderlayCapture)
        capture.user=Mock();capture.kernel=Mock();capture._pending=None
        capture.user.GetWindowThreadProcessId.return_value=123
        capture.kernel.GetCurrentThreadId.return_value=456
        release=threading.Event();calls=[]
        def render(hwnd,rect):
            calls.append(hwnd);release.wait(5);return 'rendered'
        capture._render_sync=render
        started=time.monotonic()
        try:
            self.assertIsNone(capture._render(1,(0,0,100,100)))
            for _ in range(20):self.assertIsNone(capture._render(1,(0,0,100,100)))
            self.assertLess(time.monotonic()-started,.7)
            self.assertEqual(calls,[1])
        finally:
            pending=capture._pending;release.set();pending[0].wait(2)


if __name__=='__main__':unittest.main()
