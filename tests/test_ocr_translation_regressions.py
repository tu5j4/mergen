"""Model indirmeden OCR korumasını ve çeviri yollarını doğrular."""
import unittest
from collections import OrderedDict
from unittest.mock import MagicMock, patch

import numpy as np

from app.config import Settings
from app.core.bubbles import Bubble
from app.core.ocr import OCREngine
from app.core.translator import Translator
from app.core.glossary import missing_terms


class OCRRegressionTests(unittest.TestCase):
    def test_english_auto_uses_paddle_gpu_without_loading_easyocr(self):
        easy, paddle, paddleocr = MagicMock(), MagicMock(), MagicMock()
        paddle.is_compiled_with_cuda.return_value = True
        settings = Settings()
        settings.use_paddle_cjk = False  # Chinese toggle must not disable English.
        with patch.dict('sys.modules', {'easyocr': easy, 'paddle': paddle, 'paddleocr': paddleocr}), patch('app.core.ocr.resolve_gpu', return_value=False):
            engine = OCREngine('en', settings)
        self.assertEqual(engine.paddle_device, 'gpu:0')
        self.assertIsNone(engine.reader)
        self.assertEqual(paddleocr.PaddleOCR.call_args.kwargs['lang'], 'en')
        self.assertEqual(paddleocr.PaddleOCR.call_args.kwargs['text_recognition_model_name'], 'PP-OCRv5_mobile_rec')
        easy.Reader.assert_not_called()

    def test_legacy_easyocr_selection_routes_to_paddle(self):
        easy, paddle, paddleocr = MagicMock(), MagicMock(), MagicMock()
        settings = Settings()
        settings.ocr_engine = 'easyocr'
        with patch.dict('sys.modules', {'easyocr': easy, 'paddle': paddle, 'paddleocr': paddleocr}):
            engine = OCREngine('en', settings)
        self.assertIsNotNone(engine.paddle)
        easy.Reader.assert_not_called()
        paddleocr.PaddleOCR.assert_called_once()

    def test_paddle_failure_reports_actionable_error_without_easyocr(self):
        easy, paddle, paddleocr = MagicMock(), MagicMock(), MagicMock()
        paddleocr.PaddleOCR.side_effect = RuntimeError('test unavailable')
        with patch.dict('sys.modules', {'easyocr': easy, 'paddle': paddle, 'paddleocr': paddleocr}), patch('app.core.ocr.resolve_gpu', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'bagliliklar.bat'):
                OCREngine('en', Settings())
        easy.Reader.assert_not_called()

    def test_korean_uses_its_own_recognizer(self):
        paddle, paddleocr = MagicMock(), MagicMock()
        with patch.dict('sys.modules', {'paddle': paddle, 'paddleocr': paddleocr}):
            OCREngine('ko', Settings())
        self.assertEqual(paddleocr.PaddleOCR.call_args.kwargs['text_recognition_model_name'], 'korean_PP-OCRv5_mobile_rec')
        self.assertFalse(paddleocr.PaddleOCR.call_args.kwargs['use_textline_orientation'])

    def test_other_languages_keep_orientation_classifier(self):
        for lang in ('en', 'zh', 'zh_tw', 'ja'):
            paddle, paddleocr = MagicMock(), MagicMock()
            settings = Settings()
            settings.use_manga_ocr = False
            with patch.dict('sys.modules', {'paddle': paddle, 'paddleocr': paddleocr}):
                OCREngine(lang, settings)
            self.assertTrue(paddleocr.PaddleOCR.call_args.kwargs['use_textline_orientation'])

    def test_manga_cpu_isolation_and_close(self):
        paddle, paddleocr, client = MagicMock(), MagicMock(), MagicMock()
        settings = Settings()
        settings.manga_device = 'cpu'
        client.return_value.device = 'cpu'
        with patch.dict('sys.modules', {'paddle': paddle, 'paddleocr': paddleocr}), patch('app.core.manga_client.MangaClient', client):
            engine = OCREngine('ja', settings)
        client.assert_called_once_with('cpu')
        self.assertFalse(engine.gpu)
        engine.close()
        engine.close()
        client.return_value.close.assert_called_once()

    def test_confident_columns_are_not_replaced_by_bubble_retry(self):
        engine = object.__new__(OCREngine)
        engine.s = Settings()
        engine.paddle = None  # Herhangi bir yeniden okuma testin hata vermesini sağlar.
        data = {"rec_boxes": [[100, 20, 130, 170]],
                "rec_texts": ["別買什麼花"], "rec_scores": [0.94]}
        result = engine._split_paddle_bubble_regions(
            np.full((300, 300, 3), 255, np.uint8), data,
            [Bubble(90, 10, 150, 100)])
        self.assertEqual(result, data)

    def test_failed_prediction_is_not_an_empty_success(self):
        engine = object.__new__(OCREngine)
        engine.s, engine.lang = Settings(), 'zh_tw'
        engine.s.bubble_detection = False
        engine.paddle = MagicMock()
        engine.paddle.predict.side_effect = RuntimeError('prediction failed')
        with self.assertRaisesRegex(RuntimeError, 'prediction failed'):
            engine._process_paddle(np.full((100, 100, 3), 255, np.uint8), 3)


class TranslationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.translator = object.__new__(Translator)
        self.translator.beam_size = 4
        self.translator.cache_size = 20
        self.translator._cache = OrderedDict()
        self.calls = []

        def translate_texts(texts, source, target, beam):
            self.calls.append((source, target, beam))
            return ["translated" for _ in texts]

        self.translator._translate_texts = translate_texts

    def test_chinese_route_and_cache_do_not_mix(self):
        self.translator.translate(["測試"], "zho_Hant", via_english=True)
        self.assertEqual(self.calls, [("zho_Hant", "eng_Latn", 4),
                                     ("eng_Latn", "tur_Latn", 4)])
        self.translator.translate(["測試"], "zho_Hant", via_english=True)
        self.assertEqual(len(self.calls), 2)
        self.translator.translate(["測試"], "zho_Hant", via_english=False)
        self.assertEqual(self.calls[-1], ("zho_Hant", "tur_Latn", 4))
        self.translator.translate(["測試"], "zho_Hant", beam_size=2, via_english=True)
        self.assertEqual(self.calls[-1], ("eng_Latn", "tur_Latn", 2))

    def test_english_and_japanese_keep_direct_route(self):
        self.translator.translate(["Hello"], "eng_Latn")
        self.translator.translate(["こんにちは"], "jpn_Jpan")
        self.assertEqual(self.calls, [("eng_Latn", "tur_Latn", 4),
                                     ("jpn_Jpan", "tur_Latn", 4)])

    def test_only_suspicious_sentence_retries(self):
        calls = []

        def translate_texts(texts, source, target, beam):
            calls.append((list(texts), source, target))
            if source == "zho_Hant" and target == "tur_Latn":
                return ["Anneme aldım.", "Merhaba."]
            if target == "eng_Latn":
                return ["I bought it for my grandfather."]
            return ["Dedeme aldım."]

        self.translator._translate_texts = translate_texts
        result = self.translator.translate(["買給爺爺", "你好"], "zho_Hant")
        self.assertEqual(result, ["Dedeme aldım.", "Merhaba."])
        self.assertEqual(calls[1][0], ["買給爺爺"])
        self.assertEqual(calls[2][0], ["I bought it for my grandfather."])
        self.assertEqual(self.translator.last_retry_count, 1)

    def test_unresolved_meaning_is_marked_not_replaced(self):
        self.translator._translate_texts = lambda texts, src, tgt, beam: ["Mom." if tgt == "eng_Latn" else "Anneme aldım." for t in texts]
        self.assertEqual(self.translator.translate(["買給爺爺"], "zho_Hant"), ["[?] Anneme aldım."])


class GlossaryTests(unittest.TestCase):
    def test_supported_languages_and_turkish_inflections(self):
        sources = {"eng_Latn": "My grandfather", "zho_Hant": "爺爺",
                   "zho_Hans": "爷爷", "jpn_Jpan": "おじいさん", "kor_Hang": "할아버지"}
        for language, source in sources.items():
            self.assertEqual(missing_terms(source, "Anneme aldım.", language), {"grandfather"})
            self.assertEqual(missing_terms(source, "Büyükbabamı gördüm.", language), set())

    def test_grandmother_does_not_match_mother(self):
        self.assertEqual(missing_terms("grandmother", "Babaannem geldi.", "eng_Latn"), set())

    def test_unchanged_numbers_and_no_anchors(self):
        self.assertEqual(missing_terms("14 m", "14 metre", "eng_Latn"), set())
        self.assertEqual(missing_terms("14 m", "40 metre", "eng_Latn"), {"number:14"})
        self.assertEqual(missing_terms("Hello", "Merhaba", "eng_Latn"), set())


if __name__ == "__main__":
    unittest.main()
