import unittest
from concurrent.futures import Future
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import cv2
import numpy as np

from app.config import LANGS, Settings
from app.core.bubbles import Bubble, open_white_edge
from app.core.ocr import OCRBlock, OCREngine
from app.core.panels import Panel, detect_panels, order_by_panel, panel_id
from app.core.pipeline import TranslationWorker
from app.core.textgroup import Box, group_boxes


class PanelTests(unittest.TestCase):
    def test_only_korean_groups_widely_spaced_lines_in_known_balloon(self):
        boxes = [Box(60, 50, 200, 70, 'first'), Box(80, 92, 180, 112, 'second')]
        balloon = Bubble(40, 30, 220, 140)
        for lang in ('ko', 'en', 'ja', 'zh', 'zh_tw'):
            engine = object.__new__(OCREngine)
            engine.s, engine.lang = Settings(), lang
            groups = engine._layout_groups(boxes, [balloon], [])
            self.assertEqual(len(groups), 1 if lang == 'ko' else 2)
        self.assertEqual(len(group_boxes(boxes, bubble_ids=[None, None], same_bubble_gap_ratio=1.25)), 2)
        self.assertEqual(len(group_boxes(boxes, bubble_ids=[0, 1], same_bubble_gap_ratio=1.25)), 2)

    def test_every_language_expands_scroll_strip_to_whole_balloon(self):
        image = np.full((600, 300, 3), 255, np.uint8)
        for lang in ('ko', 'en', 'ja', 'zh', 'zh_tw'):
            worker = TranslationWorker(Settings(), True)
            worker.processed = [[0, 400]]
            worker._executor = MagicMock()
            with patch('app.core.bubbles.detect_bubbles', return_value=[Bubble(40, 200, 250, 550)]):
                worker._maybe_submit(image, lang, False)
            args = worker._executor.submit.call_args.args
            self.assertEqual(args[2], 192)
            self.assertEqual(args[1].shape[0], 408)

    def test_failed_scan_retries_twice_without_caching_failed_page(self):
        worker = TranslationWorker(Settings(), True)
        worker._attempted_scroll = 0
        worker.content_blocks = [{'text': 'already displayed'}]
        for attempt in range(3):
            worker._attempted_scroll = 0
            worker._job = Future()
            worker._job.set_exception(RuntimeError('test prediction failure'))
            with patch('app.core.pipeline.traceback.print_exc'):
                worker._check_job()
            self.assertEqual(worker.processed, [])
            self.assertEqual(worker._attempted_scroll, None if attempt < 2 else 0)
        self.assertEqual(worker.content_blocks, [{'text': 'already displayed'}])

    def test_empty_translation_is_not_marked_processed(self):
        worker = TranslationWorker(Settings(), True)
        worker.ocr = SimpleNamespace(process_iter=lambda *args: iter([
            [OCRBlock(20, 20, 50, 90, '測試')]]))
        worker.translator = SimpleNamespace(translate=lambda *a, **kw: [''])
        with patch.object(worker, '_write_scan_diagnostic'), self.assertRaisesRegex(RuntimeError, 'boş sonuç'):
            worker._ocr_job(np.full((100, 100, 3), 255, np.uint8), 0, 0, 'zh_tw', 4)
        self.assertEqual(worker.processed, [])

    def test_grid_and_language_reading_order(self):
        image = np.full((500, 500, 3), 255, np.uint8)
        for x in (20, 270):
            for y in (20, 270):
                cv2.rectangle(image, (x, y), (x+210, y+210), (0, 0, 0), 4)
                cv2.line(image, (x+30, y+30), (x+160, y+160), (0, 0, 0), 5)
        panels = detect_panels(image)
        self.assertEqual(len(panels), 4)
        blocks = [OCRBlock(x, y, x+30, y+50, str(i)) for i, (x, y) in enumerate(
            [(60, 60), (310, 60), (60, 310), (310, 310)])]
        self.assertEqual([b.text for b in order_by_panel(blocks, panels, True)], ['1', '0', '3', '2'])
        self.assertEqual([b.text for b in order_by_panel(blocks, panels, False)], ['0', '1', '2', '3'])

    def test_blank_page_and_cross_panel_title(self):
        image = np.full((200, 300, 3), 255, np.uint8)
        self.assertEqual(len(detect_panels(image)), 1)
        self.assertIsNone(panel_id(Box(80, 10, 220, 50), [Panel(0, 0, 130, 200), Panel(170, 0, 300, 200)]))

    def test_unassigned_caption_is_not_sent_to_end_of_page(self):
        panels = [Panel(0, 100, 200, 300)]
        blocks = [OCRBlock(20, 140, 80, 200, 'later'), OCRBlock(20, 10, 80, 60, 'first')]
        self.assertEqual([b.text for b in order_by_panel(blocks, panels)], ['first', 'later'])

    def test_neighboring_panels_never_merge(self):
        boxes = [Box(80, 20, 100, 80), Box(103, 20, 123, 80)]
        self.assertEqual(len(group_boxes(boxes, panel_ids=[0, 1])), 2)

    def test_panel_batches_keep_balloon_texts_independent(self):
        engine = object.__new__(OCREngine)
        engine.info = LANGS['zh_tw']
        panels = [Panel(0, 0, 200, 200), Panel(220, 0, 420, 200)]
        blocks = [OCRBlock(20, 20, 60, 90, 'left'), OCRBlock(250, 20, 290, 90, 'right')]
        batches = list(engine._panel_batches(blocks, panels))
        self.assertEqual([[b.text for b in batch] for batch in batches], [['right'], ['left']])

    def test_duplicate_column_removed_but_distant_repetition_kept(self):
        engine = object.__new__(OCREngine)
        engine.s, engine.lang = Settings(), 'zh_tw'
        boxes = [Box(40, 30, 60, 100, '測試', .9), Box(42, 32, 62, 102, '測試', .8),
                 Box(140, 30, 160, 100, '測試', .95)]
        groups = engine._layout_groups(boxes, [], [Panel(0, 0, 300, 300)])
        self.assertEqual(sum(map(len, groups)), 2)

    def test_partial_panel_does_not_hide_complete_balloon(self):
        text = Box(40, 40, 70, 100)
        self.assertFalse(OCREngine._cut_region(40, 40, 70, 100, 300, 300, 3,
                                             [text], [Bubble(25, 20, 90, 130)])[0])

    def test_clipped_balloon_and_horizontal_text_edge_wait(self):
        text = Box(40, 20, 70, 80)
        result = OCREngine._cut_region(40, 20, 70, 80, 300, 300, 3,
                                      [text], [Bubble(25, 0, 90, 100)])
        self.assertEqual(result[:2], (True, True))
        self.assertTrue(OCREngine._cut_region(0, 40, 20, 100, 300, 300, 3,
                                            [Box(0, 40, 20, 100)], [])[0])

    def test_open_white_balloon_at_viewport_edge_waits_without_closed_contour(self):
        image = np.zeros((250, 300, 3), np.uint8)
        cv2.ellipse(image, (150, 35), (65, 75), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(image, (150, 35), (65, 75), 0, 0, 360, (0, 0, 0), 2)
        text = Box(130, 30, 170, 80)
        self.assertTrue(open_white_edge(image, text, 'top'))
        result = OCREngine._cut_region(130, 30, 170, 80, 300, 250, 3,
                                      [text], [], rgb=image)
        self.assertEqual(result[4], frozenset({'top'}))
        self.assertFalse(OCREngine._cut_region(130, 30, 170, 80, 300, 250, 3,
                                              [text], [], rgb=image,
                                              viewport_edges=frozenset({'left', 'right'}))[0])
        self.assertFalse(open_white_edge(np.full_like(image, 255), text, 'top'))
        panel = np.zeros_like(image)
        cv2.rectangle(panel, (95, 0), (205, 200), (255, 255, 255), -1)
        self.assertFalse(open_white_edge(panel, text, 'top'))

    def test_side_cut_does_not_hide_complete_balloons_below(self):
        worker = TranslationWorker(Settings(), True)
        worker.ocr = SimpleNamespace(process_iter=lambda *args: iter([[
            OCRBlock(270, 30, 300, 100, '', cut=True,
                     cut_edges=frozenset({'right'})),
            OCRBlock(50, 160, 120, 220, 'hello')]]))
        worker.translator = SimpleNamespace(translate=lambda texts, *a, **kw: ['merhaba'])
        gen, top, bottom = worker._ocr_job(np.full((300, 300, 3), 255, np.uint8),
                                           0, worker._gen, 'en', 2)
        self.assertEqual((top, bottom), (0, 300))
        self.assertEqual(worker._partials.get_nowait()[1][0]['src'], 'hello')

    def test_both_vertical_cuts_leave_middle_for_translation(self):
        worker = TranslationWorker(Settings(), True)
        worker.ocr = SimpleNamespace(process_iter=lambda *args: iter([[
            OCRBlock(50, 0, 100, 60, '', cut=True,
                     cut_edges=frozenset({'top'})),
            OCRBlock(50, 120, 100, 180, 'hello'),
            OCRBlock(50, 260, 100, 300, '', cut=True,
                     cut_edges=frozenset({'bottom'}))]]))
        worker.translator = SimpleNamespace(translate=lambda texts, *a, **kw: ['merhaba'])
        gen, top, bottom = worker._ocr_job(np.full((300, 300, 3), 255, np.uint8),
                                           0, worker._gen, 'en', 2)
        self.assertEqual((top, bottom), (61, 259))

    def test_artificial_strip_cut_gets_one_full_viewport_retry(self):
        worker = TranslationWorker(Settings(), True)
        worker._executor = MagicMock()
        calls = []
        def scan(*args):
            calls.append(args[2])
            yield [OCRBlock(40, 0, 100, 70, '', cut=True,
                            cut_edges=frozenset({'top'}))]
        worker.ocr = SimpleNamespace(process_iter=scan)
        worker.translator = SimpleNamespace(translate=lambda *a, **kw: self.fail('cut text translated'))
        result = worker._ocr_job(np.full((200, 300, 3), 255, np.uint8), 200,
                                 worker._gen, 'en', 2, None, (0, 400))
        self.assertEqual(calls, [frozenset({'left', 'right', 'bottom'})])
        worker._job = Future()
        worker._job.set_result(result)
        worker._check_job()
        self.assertTrue(worker._retry_full_viewport)
        worker._maybe_submit(np.full((400, 300, 3), 255, np.uint8), 'en', False)
        args = worker._executor.submit.call_args.args
        self.assertEqual(args[2], 0)
        self.assertEqual(args[1].shape[0], 400)
        self.assertFalse(worker._retry_full_viewport)

    def test_paddle_emits_cut_marker_without_model(self):
        engine = object.__new__(OCREngine)
        engine.s, engine.lang, engine.info = Settings(), 'zh_tw', LANGS['zh_tw']
        engine.s.bubble_detection = False
        engine.paddle = SimpleNamespace(predict=lambda rgb: iter([{'rec_boxes': [[50, 0, 80, 80]],
            'rec_texts': ['測試'], 'rec_scores': [.95]}]))
        blocks = engine._process_paddle(np.full((300, 300, 3), 255, np.uint8), 3)
        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0].cut)
        self.assertTrue(blocks[0].cut_top)

    def test_cut_span_not_marked_processed_and_only_complete_text_translated(self):
        batches = [[OCRBlock(20, 20, 50, 90, 'hello')],
                   [OCRBlock(20, 180, 50, 300, '', cut=True)]]
        calls = []
        worker = TranslationWorker(Settings(), True)
        worker.ocr = SimpleNamespace(process_iter=lambda *args: iter(batches))
        worker.translator = SimpleNamespace(translate=lambda texts, *a, **kw: calls.append(texts) or ['merhaba'])
        gen, top, bottom = worker._ocr_job(np.full((300, 300, 3), 255, np.uint8), 100, worker._gen, 'en', 2)
        self.assertEqual((top, bottom), (100, 279))
        self.assertEqual(calls, [['hello']])

    def test_only_english_batches_across_panels_and_flushes_remainder(self):
        for lang in ('en', 'ja', 'ko', 'zh', 'zh_tw'):
            with self.subTest(lang=lang):
                worker = TranslationWorker(Settings(), True)
                worker.s.translate_chunk = 3
                batches = [[OCRBlock(20, 20+i*30, 50, 40+i*30, str(i))] for i in range(7)]
                batches.insert(2, [OCRBlock(20, 280, 50, 300, '', cut=True)])
                worker.ocr = SimpleNamespace(process_iter=lambda *args: iter(batches))
                calls = []
                worker.translator = SimpleNamespace(translate=lambda texts, *a, **kw: calls.append(list(texts)) or list(texts))
                worker._ocr_job(np.full((300, 300, 3), 255, np.uint8), 0, worker._gen, lang, 4)
                self.assertEqual([len(c) for c in calls], [3, 3, 1] if lang == 'en' else [1]*7)
                self.assertEqual([t for c in calls for t in c], [str(i) for i in range(7)])
                items = []
                while not worker._partials.empty():
                    items.extend(worker._partials.get_nowait()[1])
                self.assertEqual([b['src'] for b in items], [str(i) for i in range(7)])

    def test_english_cancel_discards_pending_balloon(self):
        worker = TranslationWorker(Settings(), True)
        worker.s.translate_chunk = 3
        def batches(*args):
            yield [OCRBlock(20, 20, 50, 80, 'hello')]
            worker._gen += 1
        worker.ocr = SimpleNamespace(process_iter=batches)
        worker.translator = SimpleNamespace(translate=lambda *a, **kw: self.fail('Cancelled job translated pending text'))
        self.assertEqual(worker._ocr_job(np.full((300, 300, 3), 255, np.uint8), 0, worker._gen, 'en', 4)[1:], (None, None))


if __name__ == '__main__':
    unittest.main()
