import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from app.config import Settings, LANGS
from app.core.manga_client import MangaClient, worker_environment
from app.core.ocr import OCREngine, OCRBlock
from app.core.panels import Panel


class MangaIsolationTests(unittest.TestCase):
    def test_child_environment_drops_parent_cuda_dll_paths(self):
        with patch.dict(os.environ, {'PATH': os.pathsep.join([
            'C:/Windows/System32', 'C:/app/.venv/Lib/site-packages/nvidia/cublas/bin',
            'C:/app/.venv/Lib/site-packages/torch/lib']), 'PYTHONPATH': 'bad'}):
            env = worker_environment()
        self.assertEqual(env['PATH'], 'C:/Windows/System32')
        self.assertNotIn('PYTHONPATH', env)

    def test_client_empty_batch_does_not_start_inference(self):
        client = object.__new__(MangaClient)
        client._process = None
        self.assertEqual(client.recognize([]), [])
        with self.assertRaises(ValueError):
            client.recognize([Image.new('RGB', (5, 5))]*5)

    def test_manga_batches_capped_at_four(self):
        engine = object.__new__(OCREngine)
        engine.s = Settings()
        engine.s.manga_batch = 16
        engine.manga = MagicMock()
        engine.manga.recognize.side_effect = lambda crops: ['text']*len(crops)
        self.assertEqual(len(engine._manga_batch([Image.new('RGB', (10, 10))]*9)), 9)
        self.assertEqual([len(c.args[0]) for c in engine.manga.recognize.call_args_list], [4, 4, 1])

    def test_helper_failure_keeps_paddle_and_cut_marker(self):
        engine = object.__new__(OCREngine)
        engine.s, engine.lang, engine.info = Settings(), 'ja', LANGS['ja']
        engine.s.ja_dense_split = False
        engine.manga = MagicMock()
        engine.manga.recognize.side_effect = RuntimeError('test failure')
        source = [OCRBlock(20, 20, 80, 90, 'こんにちは'), OCRBlock(20, 170, 80, 200, '', cut=True)]
        engine._process_paddle = lambda *a: source
        output = [b for batch in engine._iter_paddle_manga(np.full((200, 200, 3), 255, np.uint8), 3,
            [Panel(0, 0, 200, 200)]) for b in batch]
        self.assertEqual(output[0].text, 'こんにちは')
        self.assertTrue(output[1].cut)
        self.assertEqual(len(engine.manga.recognize.call_args.args[0]), 1)


if __name__ == '__main__':
    unittest.main()
