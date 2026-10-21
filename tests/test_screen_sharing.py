import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from app.config import Settings
from app.core.pipeline import TranslationWorker
from app.ui.overlay import OverlayWindow


class ScreenSharingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shared_overlay_does_not_exclude_itself(self):
        window = OverlayWindow(Settings())
        try:
            with patch('app.ui.overlay.exclude_from_capture', return_value=True) as affinity:
                window.ensure_platform_setup()
                affinity.assert_called_once_with(window, excluded=False)
                self.assertFalse(window.is_capture_excluded())
        finally:
            window.close()

    def test_private_overlay_uses_capture_exclusion(self):
        window = OverlayWindow(Settings(share_translations=False))
        try:
            with patch('app.ui.overlay.exclude_from_capture', return_value=True) as affinity:
                window.ensure_platform_setup()
                affinity.assert_called_once_with(window)
                self.assertTrue(window.is_capture_excluded())
        finally:
            window.close()

    def worker(self, excluded=False, content=True):
        worker = TranslationWorker(Settings(), excluded)
        worker._overlay_has_content = content
        worker.hide_request = Mock()
        worker._hide_ack = Mock()
        worker._hide_ack.wait.return_value = True
        return worker

    def test_shared_capture_waits_for_hidden_overlay_then_restores(self):
        worker = self.worker()
        capture = Mock()
        events = []
        worker.hide_request.emit.side_effect = lambda hidden: events.append(hidden)
        capture.grab.side_effect = lambda *args: events.append('capture') or 'image'
        with patch('app.core.pipeline.time.sleep'):
            self.assertEqual(worker._grab(capture, (0, 0, 100, 100)), 'image')
        self.assertEqual(events, [True, 'capture', False])
        worker._hide_ack.wait.assert_called_once_with(.5)

    def test_timeout_skips_capture_and_restores_overlay(self):
        worker = self.worker()
        worker._hide_ack.wait.return_value = False
        capture = Mock()
        self.assertIsNone(worker._grab(capture, (0, 0, 100, 100)))
        capture.grab.assert_not_called()
        self.assertEqual([c.args[0] for c in worker.hide_request.emit.call_args_list], [True, False])

    def test_capture_error_still_restores_overlay(self):
        worker = self.worker()
        capture = Mock()
        capture.grab.side_effect = RuntimeError('capture failed')
        with patch('app.core.pipeline.time.sleep'), self.assertRaises(RuntimeError):
            worker._grab(capture, (0, 0, 100, 100))
        self.assertEqual([c.args[0] for c in worker.hide_request.emit.call_args_list], [True, False])

    def test_excluded_overlay_does_not_need_hiding(self):
        worker = self.worker(excluded=True)
        worker._grab(Mock(), (0, 0, 100, 100))
        worker.hide_request.emit.assert_not_called()
        worker._hide_ack.wait.assert_not_called()

    def test_empty_overlay_does_not_need_hiding(self):
        worker = self.worker(content=False)
        worker._grab(Mock(), (0, 0, 100, 100))
        worker.hide_request.emit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
