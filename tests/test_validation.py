import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.config import Settings
from installer import service
from app.child_process import external_environment

class ValidationTests(unittest.TestCase):
    def test_missing_models_are_reported_separately(self):
        settings=Settings(source_lang='ja',translation_backend='cpu',ocr_backend='cpu',manga_backend='cpu',use_manga_ocr=True)
        with tempfile.TemporaryDirectory() as directory,patch.object(service,'DATA_ROOT',Path(directory)),patch.object(service,'component_ready',return_value=False),patch('app.core.runtime_client.RuntimeClient') as client:
            report=service.validate(settings,lambda _:None)
            self.assertFalse(report['ok'])
            self.assertEqual([r['status'] for r in report['rows']],['missing']*3)
            client.assert_not_called()
            self.assertTrue((Path(directory)/'last-validation.json').is_file())

    def test_failure_does_not_hide_remaining_results(self):
        settings=Settings(source_lang='ja',translation_backend='cpu',ocr_backend='cpu',manga_backend='cpu',use_manga_ocr=True)
        calls=[]
        class FakeClient:
            device='cpu'
            def __init__(self,task,*args,**kwargs):
                calls.append(task)
                if task=='translate':raise RuntimeError('test model error')
            def predict(self,image):yield {'rec_texts':['HELLO WORLD']}
            def recognize(self,crops):return ['こんにちは']
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory,patch.object(service,'DATA_ROOT',Path(directory)),patch.object(service,'component_ready',return_value=True),patch('app.core.runtime_client.RuntimeClient',FakeClient):
            report=service.validate(settings,lambda _:None)
            self.assertFalse(report['ok'])
            self.assertEqual(calls,['translate','ocr','manga'])
            self.assertEqual([r['status'] for r in report['rows']],['failed','passed','passed'])

    def test_translation_uses_selected_source_language(self):
        settings=Settings(source_lang='ko',translation_backend='cpu',ocr_backend='cpu',manga_backend='cpu',use_manga_ocr=False)
        requests=[]
        class FakeClient:
            device='cpu'
            def __init__(self,task,*args,**kwargs):self.task=task
            def request(self,**kwargs):requests.append(kwargs);return ['merhaba, nasılsın?']
            def predict(self,image):yield {'rec_texts':['안녕하세요']}
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory,patch.object(service,'DATA_ROOT',Path(directory)),patch.object(service,'component_ready',return_value=True),patch('app.core.runtime_client.RuntimeClient',FakeClient):
            report=service.validate(settings,lambda _:None)
            self.assertTrue(report['ok'])
            self.assertEqual(requests[0]['source'],'kor_Hang')

    def test_frozen_ui_paths_removed_from_child_environment(self):
        import sys
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS','C:/fake/ui/_internal',create=True):
            result=external_environment({'PATH':'C:/fake/ui/_internal;C:/fake/ui/_internal/PySide6;C:/Windows/System32','PYTHONHOME':'bad','PYTHONPATH':'bad'})
        self.assertNotIn('PYTHONHOME',result);self.assertNotIn('PYTHONPATH',result)
        self.assertEqual(result['PATH'],'C:/Windows/System32')
        self.assertEqual(result['PYTHONUNBUFFERED'],'1')
