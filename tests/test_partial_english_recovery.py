"""Partial English balloon recovery, with deterministic OCR outputs and no models."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from app.config import LANGS, Settings
from app.core.bubbles import Bubble
from app.core.ocr import OCREngine
from app.core.pipeline import TranslationWorker
from app.core.textgroup import Box


def result(boxes, texts, scores):
    return {'rec_boxes': boxes, 'rec_texts': texts, 'rec_scores': scores}


class EnglishRecoveryTests(unittest.TestCase):
    def engine(self):
        engine = object.__new__(OCREngine)
        engine.s, engine.lang, engine.info = Settings(), 'en', LANGS['en']
        engine.paddle = Mock()
        return engine

    def image(self):
        image = np.full((600, 400, 3), 255, np.uint8)
        cv2.rectangle(image, (30, 30), (300, 200), (0, 0, 0), 2)
        cv2.putText(image, 'First line', (70, 80), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 1)
        cv2.putText(image, 'Missing words', (70, 106), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 1)
        return image, Bubble(30, 30, 300, 200)

    def test_missing_line_is_recovered_before_grouping_and_translation(self):
        engine = self.engine()
        image, balloon = self.image()
        engine.paddle.predict.side_effect = [
            iter([result([[68, 63, 200, 83]], ['First line'], [.96])]),
            iter([result([[38, 33, 170, 53], [38, 59, 200, 79]],
                         ['First line', 'Missing words'], [.97, .96])]),
        ]
        with patch('app.core.ocr.detect_bubbles', return_value=[balloon]):
            blocks = engine._process_paddle(image, 3, panels=[])
        self.assertEqual(engine.paddle.predict.call_count, 2)
        self.assertEqual(engine.last_english_retry_count, 1)
        self.assertEqual(engine.last_english_recovered_count, 1)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].text, 'First line Missing words')
        self.assertFalse(blocks[0].cut)

    def test_fully_read_balloon_does_not_cost_an_extra_pass(self):
        engine = self.engine()
        image, balloon = self.image()
        boxes = [Box(68, 63, 200, 83, 'First line', .96),
                 Box(68, 89, 230, 109, 'Missing words', .96)]
        engine._retry_english_bubbles(image, boxes, [], [balloon], 3)
        engine.paddle.predict.assert_not_called()

    def test_entirely_missed_text_can_be_recovered(self):
        engine = self.engine()
        image, balloon = self.image()
        engine.paddle.predict.return_value = iter([result([[38, 33, 170, 53]], ['First line'], [.96])])
        boxes = []
        engine._retry_english_bubbles(image, boxes, [], [balloon], 3)
        self.assertEqual([b.text for b in boxes], ['First line'])

    def test_weak_retry_cannot_overwrite_a_strong_reading(self):
        engine = self.engine()
        image, balloon = self.image()
        original = Box(68, 63, 200, 83, 'First line', .96)
        engine.paddle.predict.return_value = iter([result([[38, 33, 170, 53], [38, 59, 200, 79]],
                                                        ['Wrong reading', 'Uncertain text'], [.99, .60])])
        boxes = [original]
        engine._retry_english_bubbles(image, boxes, [], [balloon], 3)
        self.assertEqual(boxes, [original])

    def test_failed_optional_retry_keeps_existing_text(self):
        engine = self.engine()
        image, balloon = self.image()
        original = Box(68, 63, 200, 83, 'First line', .96)
        engine.paddle.predict.side_effect = RuntimeError('test failure')
        boxes = [original]
        with patch('builtins.print'):
            engine._retry_english_bubbles(image, boxes, [], [balloon], 3)
        self.assertEqual(boxes, [original])

    def test_clipped_balloon_is_never_retried(self):
        engine = self.engine()
        image, _ = self.image()
        weak = Box(68, 63, 200, 83, 'First line', .4)
        engine._retry_english_bubbles(image, [weak], [weak], [Bubble(30, 0, 300, 200)], 3)
        engine.paddle.predict.assert_not_called()

    def test_retry_budget_is_two_balloons_per_scan(self):
        engine = self.engine()
        image = np.full((900, 400, 3), 255, np.uint8)
        balloons = [Bubble(30, y, 300, y+180) for y in (30, 300, 600)]
        weak = [Box(70, y+40, 200, y+60, 'weak', .4) for y in (30, 300, 600)]
        engine.paddle.predict.side_effect = lambda crop: iter([result([], [], [])])
        engine._retry_english_bubbles(image, list(weak), weak, balloons, 3)
        self.assertEqual(engine.paddle.predict.call_count, 2)

    def test_untextured_white_space_and_scenery_are_not_retried(self):
        engine = self.engine()
        for image in (np.full((600, 400, 3), 255, np.uint8), np.zeros((600, 400, 3), np.uint8)):
            engine._retry_english_bubbles(image, [], [], [Bubble(30, 30, 300, 200)], 3)
        engine.paddle.predict.assert_not_called()


class PassageUpgradeTests(unittest.TestCase):
    def block(self, source='But no matter how strong a human is', **changes):
        block = dict(x=100, y=100, w=300, h=60, src=source, text='translation',
                     source_lang='en', panel=0, bg=(255, 255, 255), vertical=False)
        block.update(changes)
        return block

    def worker(self, old):
        worker = TranslationWorker(Settings(), True)
        worker.content_blocks = list(old)
        worker._emit_visible = Mock()
        return worker

    def submit(self, worker, new, generation=None):
        worker._partials.put((worker._gen if generation is None else generation, [new]))
        worker._drain_partials()

    def test_full_passage_replaces_cached_partial_instead_of_being_dropped(self):
        old = self.block()
        full = self.block(old['src'] + ', they will grow weaker in this forest.', h=120)
        worker = self.worker([old])
        self.submit(worker, full)
        self.assertEqual(worker.content_blocks, [full])
        worker._emit_visible.assert_called_once()

    def test_same_geometry_with_more_complete_text_can_update(self):
        old = self.block()
        full = self.block(old['src'] + ', they will grow weaker.')
        worker = self.worker([old])
        self.submit(worker, full)
        self.assertEqual(worker.content_blocks, [full])

    def test_shorter_unrelated_wrong_panel_and_other_language_cannot_replace(self):
        old = self.block()
        for new in (self.block('A human is strong'), self.block('A completely different long sentence with no relationship to the old passage'),
                    self.block(old['src'] + ' for now anyway', panel=1),
                    self.block(old['src'] + ' for now anyway', source_lang='ko')):
            worker = self.worker([old])
            self.submit(worker, new)
            self.assertEqual(worker.content_blocks, [old])
            worker._emit_visible.assert_not_called()

    def test_complete_result_is_never_downgraded_and_duplicate_is_ignored(self):
        full = self.block('But no matter how strong a human is, they grow weaker.', h=120)
        worker = self.worker([full])
        self.submit(worker, self.block())
        self.submit(worker, full)
        self.assertEqual(worker.content_blocks, [full])
        worker._emit_visible.assert_not_called()

    def test_broad_box_cannot_merge_two_neighboring_passages(self):
        old, neighbor = self.block(), self.block('Another conversation entirely', y=165)
        worker = self.worker([old, neighbor])
        self.submit(worker, self.block(old['src'] + ' and some extra words', h=130))
        self.assertEqual(worker.content_blocks, [old, neighbor])

    def test_cancelled_generation_cannot_upgrade_cached_text(self):
        old = self.block()
        worker = self.worker([old])
        self.submit(worker, self.block(old['src'] + ' and some extra words'), generation=worker._gen-1)
        self.assertEqual(worker.content_blocks, [old])
        self.assertFalse(worker._session_context.history)


if __name__ == '__main__':
    unittest.main()
