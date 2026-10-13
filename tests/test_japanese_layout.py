"""Japanese-only outline-text grouping and overlay collision regressions."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from app.config import Settings
from app.core.bubbles import Bubble, bubble_id
from app.core.ocr import OCREngine
from app.core.panels import Panel
from app.core.textgroup import Box, order_boxes
from app.ui.overlay import OverlayWindow


class JapaneseGroupingTests(unittest.TestCase):
    def test_short_column_inside_verified_balloon_joins_only_in_japanese(self):
        boxes = [Box(41, 23, 67, 220, '九識心王が開くのじゃ'),
                 Box(72, 21, 99, 88, '御子の'),
                 Box(103, 20, 132, 237, 'あれと一体化したときに'),
                 Box(141, 22, 170, 126, '極限状況で')]
        for lang in ('ja', 'en', 'ko', 'zh', 'zh_tw'):
            engine = object.__new__(OCREngine)
            engine.s, engine.lang = Settings(), lang
            groups = engine._layout_groups(boxes, [Bubble(16, 15, 196, 273)], [])
            self.assertEqual(len(groups), 1 if lang == 'ja' else 3)
            if lang == 'ja':
                self.assertEqual(''.join(b.text for b in order_boxes(groups[0], True)),
                                 '極限状況であれと一体化したときに御子の九識心王が開くのじゃ')
                # Unverified/background columns still retain the height guard.
                self.assertEqual(len(engine._layout_groups(boxes, [], [])), 3)

    def test_short_columns_do_not_cross_balloon_or_panel_boundaries(self):
        engine = object.__new__(OCREngine)
        engine.s, engine.lang = Settings(), 'ja'
        boxes = [Box(50, 20, 70, 220), Box(80, 20, 100, 80)]
        bubbles = [Bubble(45, 10, 75, 230), Bubble(76, 10, 110, 100)]
        self.assertEqual(len(engine._layout_groups(boxes, bubbles, [])), 2)
        self.assertEqual(len(engine._layout_groups(
            boxes, [Bubble(40, 10, 110, 230)],
            [Panel(0, 0, 75, 250), Panel(76, 0, 150, 250)])), 2)

    def test_center_only_false_balloon_rejected_by_column_coverage(self):
        column = Box(131, 13, 222, 283)
        fragment = Bubble(152, 106, 199, 204)
        self.assertEqual(bubble_id(column, [fragment]), 0)
        self.assertIsNone(bubble_id(column, [fragment], .75))
        self.assertEqual(bubble_id(column, [Bubble(120, 0, 240, 300)], .75), 0)

    def test_japanese_outline_columns_form_two_rtl_groups_only(self):
        boxes = [Box(131, 13, 222, 283, 'L1', .76), Box(107, 24, 149, 334, 'L2', .79),
                 Box(741, 10, 819, 277, 'R1', .81), Box(703, 19, 754, 269, 'R2', .88)]
        fragments = [Bubble(152, 106, 199, 204), Bubble(757, 85, 792, 165)]
        for lang in ('ja', 'en', 'ko', 'zh', 'zh_tw'):
            engine = object.__new__(OCREngine)
            engine.s, engine.lang = Settings(), lang
            groups = engine._layout_groups(boxes, fragments, [Panel(0, 0, 879, 1265)])
            self.assertEqual(len(groups), 2 if lang == 'ja' else 4)
            if lang == 'ja':
                self.assertCountEqual([[b.text for b in order_boxes(g, True)] for g in groups],
                                      [['L1', 'L2'], ['R1', 'R2']])

    def test_real_separate_balloons_still_separate(self):
        engine = object.__new__(OCREngine)
        engine.s, engine.lang = Settings(), 'ja'
        boxes = [Box(50, 20, 70, 160), Box(80, 20, 100, 160)]
        bubbles = [Bubble(45, 10, 75, 180), Bubble(76, 10, 110, 180)]
        self.assertEqual(len(engine._layout_groups(boxes, bubbles, [])), 2)


class JapaneseOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_overlapping_columns_reserve_disjoint_lanes_only_for_japanese(self):
        for lang in ('ja', 'en', 'ko', 'zh', 'zh_tw'):
            overlay = OverlayWindow(Settings())
            overlay.resize(500, 400)
            overlay.set_blocks([
                dict(x=200, y=20, w=79, h=265, text='Birinci örnek çeviri.', vertical=True, source_lang=lang),
                dict(x=161, y=26, w=56, h=255, text='İkinci örnek çeviri.', vertical=True, source_lang=lang)])
            self.assertEqual(len(overlay._layout), 2)
            first, second = (item[0] for item in overlay._layout)
            self.assertEqual(first.intersects(second), lang != 'ja')
            overlay.close()


if __name__ == '__main__':
    unittest.main()
