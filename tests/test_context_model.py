import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from app.core.context_model import QwenContextModel
from scripts.prepare_context_assets import fetch
from scripts.prepare_sandbox_context import prepare
from scripts.benchmark_context import publish


class ContextModelTests(unittest.TestCase):
    def model(self):
        return QwenContextModel('missing.exe', 'missing.gguf', 'unused-logs')

    @staticmethod
    def response(values, reason='stop'):
        return {'choices': [{'finish_reason': reason, 'message': {'content': json.dumps({'translations': values})}}]}

    def test_success_is_only_a_proposal_and_preserves_draft(self):
        model = self.model()
        draft = ['teşekkürler']
        with patch.object(model, 'start'), patch.object(model, '_request', return_value=self.response(['elinize sağlık'])):
            result = model.refine(['thanks'], draft)
        self.assertEqual(result.status, 'proposal')
        self.assertEqual(result.translations, ['elinize sağlık'])
        self.assertEqual(draft, ['teşekkürler'])

    def test_timeout_closes_server_and_returns_base(self):
        model = self.model()
        with patch.object(model, 'start'), patch.object(model, '_request', side_effect=TimeoutError('timeout')), patch.object(model, 'close') as close:
            result = model.refine(['thanks'], ['teşekkürler'])
        self.assertEqual(result.status, 'fallback')
        self.assertEqual(result.translations, ['teşekkürler'])
        close.assert_called_once()

    def test_bad_count_incomplete_or_reasoning_cannot_replace_base(self):
        for response in [self.response([]), self.response(['a','b']), self.response([''], 'length'), self.response(['<think>test'])]:
            model = self.model()
            with patch.object(model, 'start'), patch.object(model, '_request', return_value=response):
                result = model.refine(['hello'], ['merhaba'])
            self.assertEqual(result.status, 'fallback')
            self.assertEqual(result.translations, ['merhaba'])

    def test_missing_assets_return_base_without_download(self):
        result = self.model().refine(['hello'], ['merhaba'])
        self.assertEqual(result.status, 'fallback')
        self.assertEqual(result.translations, ['merhaba'])

    def test_short_window_bounded_and_thinking_disabled(self):
        history = [dict(source=str(i),translation='draft') for i in range(30)]
        payload = QwenContextModel.payload(['thanks'], ['teşekkürler'], history, 'eng_Latn')
        data = json.loads(payload['messages'][1]['content'])
        self.assertEqual(len(data['previous']), 6)
        self.assertEqual(data['previous'][0]['source'], '24')
        self.assertFalse(payload['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(payload['max_tokens'], 256)

    def test_oversize_input_falls_back_before_launch(self):
        model = self.model()
        with patch.object(model, 'start') as start:
            result = model.refine(['x'*801], ['draft'])
        self.assertEqual(result.status, 'fallback')
        start.assert_not_called()

    def test_download_hash_mismatch_never_publishes(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'model.gguf'
            with patch('urllib.request.urlopen', return_value=io.BytesIO(b'wrong')):
                with self.assertRaises(ValueError):
                    fetch('https://example.invalid/model', target, '0'*64)
            self.assertFalse(target.exists())

    def test_sandbox_mapping_and_fixture_exclude_past_references(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = sqlite3.connect(root/'input.sqlite3')
            db.execute('CREATE TABLE candidates (id INTEGER,episode INTEGER,en_start REAL,en_end REAL,english TEXT,turkish TEXT)')
            for episode in (11,12):
                for i in range(15):
                    db.execute('INSERT INTO candidates VALUES (?,?,?,?,?,?)',
                        (episode*100+i,episode,i*4,i*4+3,'a short dialogue line '+str(i),'secret_reference_'+str(i)))
            db.commit();db.close()
            config = prepare(root/'input.sqlite3', root/'test')
            xml = ET.parse(config)
            mappings = xml.findall('MappedFolders/MappedFolder')
            self.assertEqual([m.findtext('ReadOnly') for m in mappings], ['true','false'])
            fixture = json.loads((root/'test/input/cases.json').read_text(encoding='utf-8'))
            self.assertEqual(len(fixture['cases']),12)
            for case in fixture['cases']:
                self.assertTrue(all('secret_reference' not in s for s in case['previous_sources']))
                payload = QwenContextModel.payload([case['source']], ['draft'], [], 'eng_Latn')
                self.assertNotIn(case['reference'],json.dumps(payload))

    def test_report_escapes_subtitle_html(self):
        with tempfile.TemporaryDirectory() as folder:
            report = dict(status='test',rows=[dict(id=1,episode=11,source='<script>alert(1)</script>',
                nllb='base',without_history='a',with_history='b',reference='ref',history=[],
                base_ms=1,without_ms=2,with_ms=3,without_status='proposal',with_status='proposal',error='')])
            publish(Path(folder), report)
            content=(Path(folder)/'rapor.html').read_text(encoding='utf-8')
            self.assertNotIn('<script>',content)
            self.assertIn('&lt;script&gt;',content)


if __name__ == '__main__':
    unittest.main()
