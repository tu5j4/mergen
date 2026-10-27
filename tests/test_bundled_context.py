import hashlib
import io
import json
from collections import OrderedDict
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.config import Settings
from app.core.session_context import SessionContext
from app.core.translator import Translator
from app import updates,config
from installer import bundled, service
from scripts import component_models
from scripts import export_next_source


class BundledContextTests(unittest.TestCase):
    def test_release_export_preserves_model_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'source'
            export_next_source.export(output)
            relative=Path('assets/bundled-models.json')
            self.assertEqual((output/relative).read_bytes(),(export_next_source.ROOT/relative).read_bytes())
            self.assertIn(relative.as_posix(),(output/'MANIFEST.sha256').read_text(encoding='utf-8'))

    def translator(self):
        t=object.__new__(Translator)
        t.context_model=True;t._runtime=Mock()
        t._runtime.request.side_effect=lambda **kw:['tr:'+text for text in kw['texts']]
        t._cache=OrderedDict();t.cache_size=20
        return t

    def test_prior_three_and_batch_order_without_mutating_session(self):
        t=self.translator();c=SessionContext()
        for s in ('one','two','three','four'):c.remember(s,'çeviri','eng_Latn')
        t.translate(['five','six'],'eng_Latn',context=c)
        calls=t._runtime.request.call_args_list
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0].kwargs['histories'],[['two','three','four'],['three','four','five']])
        self.assertEqual([d.source for d in c.history],['one','two','three','four'])

    def test_cache_depends_on_history_and_clear_and_context_toggle(self):
        t=self.translator();c=SessionContext();c.remember('one','çeviri','eng_Latn')
        t.translate(['hello'],'eng_Latn',context=c)
        t.translate(['hello'],'eng_Latn',context=c)
        self.assertEqual(t._runtime.request.call_count,1)
        c.clear();c.remember('two','çeviri','eng_Latn')
        t.translate(['hello'],'eng_Latn',context=c)
        t.translate(['hello','world'],'eng_Latn',context=None)
        self.assertEqual(t._runtime.request.call_count,3)
        self.assertEqual(t._runtime.request.call_args.kwargs['histories'],[[],[]])

    def test_bounded_batches_keep_history_and_cached_output_order(self):
        t=self.translator();c=SessionContext()
        self.assertEqual(t.translate(['one','two'],'eng_Latn',context=c),['tr:one','tr:two'])
        t._runtime.request.reset_mock()
        texts=['one','two','three','four','five','six','seven','eight','nine']
        self.assertEqual(t.translate(texts,'eng_Latn',context=c),['tr:'+text for text in texts])
        calls=t._runtime.request.call_args_list
        self.assertEqual([len(call.kwargs['texts']) for call in calls],[3,3,1])
        self.assertEqual(calls[0].kwargs['texts'],['three','four','five'])
        self.assertEqual(calls[0].kwargs['histories'],[['one','two'],['one','two','three'],['two','three','four']])
        self.assertEqual(calls[-1].kwargs['histories'],[['six','seven','eight']])
        self.assertFalse(c.history)

    def test_incomplete_batch_is_not_cached(self):
        t=self.translator();t._runtime.request.side_effect=lambda **kw:['partial']
        with self.assertRaises(RuntimeError):t.translate(['one','two'],'eng_Latn')
        self.assertFalse(t._cache)

    def test_other_languages_do_not_leak_history(self):
        t=self.translator();c=SessionContext();c.remember('hello','merhaba','eng_Latn')
        t.translate(['こんにちは'],'jpn_Jpan',context=c)
        self.assertEqual(t._runtime.request.call_args.kwargs['histories'],[[]])

    def test_model_migration_leaves_600m_alone(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            with patch.object(config,'SETTINGS_FILE',path):
                for old,expected in [('nllb-200-distilled-600M-ct2','nllb-200-distilled-600M-ct2'),
                                     ('nllb-200-distilled-1.3B-ct2','nllb-1.3b-baglam-v3')]:
                    path.write_text(json.dumps(dict(translation_model=old)),encoding='utf-8')
                    self.assertEqual(Settings.load().translation_model,expected)

    def test_context_model_readiness_never_accepts_old_ct2(self):
        state={'1300m':{'ready':True}}
        s=Settings(translation_model='nllb-1.3b-baglam-v3')
        self.assertTrue(service.component_ready(s,'translate','1300m',state))
        s.translation_model='nllb-200-distilled-1.3B-ct2'
        self.assertFalse(service.component_ready(s,'translate','1300m',state))

    def test_hash_failure_and_missing_files_do_not_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'models/test/weights';path.parent.mkdir(parents=True)
            path.write_bytes(b'good')
            rows=[dict(path='models/test/weights',bytes=4,sha256=hashlib.sha256(b'good').hexdigest())]
            with patch.object(bundled,'entries',return_value=rows),patch.object(component_models,'DATA_ROOT',root),patch.object(component_models,'download') as download:
                component_models.install_model('1300m')
                path.write_bytes(b'evil')
                with self.assertRaises(RuntimeError):component_models.install_model('1300m')
                path.unlink()
                with self.assertRaises(RuntimeError):component_models.install_model('1300m')
                download.assert_not_called()

    def test_unsafe_manifest_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(bundled,'entries',return_value=[dict(path='../outside',bytes=4,sha256='0'*64)]):
            self.assertFalse(bundled.check_component('1300m',Path(folder)))

    def payload(self):
        prefix='https://github.com/tu5j4/mergen/releases/download/v9.0.0/'
        return dict(version='9.0.0',url=prefix+'mergen-setup-9.0.0.exe',bytes=3,sha256=hashlib.sha256(b'exe').hexdigest(),
            parts=[dict(url=prefix+'mergen-setup-9.0.0-1.bin',bytes=3,sha256=hashlib.sha256(b'bin').hexdigest())])

    def test_update_downloads_all_parts_with_original_names(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,'DATA_ROOT',Path(folder)),patch.object(updates.urllib.request,'urlopen',side_effect=[io.BytesIO(b'exe'),io.BytesIO(b'bin')]):
            package=updates.download_update(self.payload(),lambda _:None)
            path=Path(package['installer'])
            self.assertEqual(path.name,'mergen-setup-9.0.0.exe')
            self.assertEqual(path.with_name('mergen-setup-9.0.0-1.bin').read_bytes(),b'bin')
            self.assertEqual(len(json.loads(Path(package['manifest']).read_text())),2)

    def test_bad_part_never_leaves_launchable_package(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,'DATA_ROOT',Path(folder)),patch.object(updates.urllib.request,'urlopen',side_effect=[io.BytesIO(b'exe'),io.BytesIO(b'bad')]):
            with self.assertRaises(ValueError):updates.download_update(self.payload(),lambda _:None)
            self.assertFalse(list(Path(folder).rglob('*.exe')))
            self.assertFalse(list(Path(folder).rglob('*.bin')))

    def test_part_cannot_reference_another_release_or_path(self):
        for url in ('https://github.com/tu5j4/mergen/releases/download/v8/wrong.bin',
                    'https://github.com/tu5j4/mergen/releases/download/v9.0.0/../bad.bin'):
            p=self.payload();p['parts'][0]['url']=url
            with self.assertRaises(ValueError):updates.package_files(p)


if __name__=='__main__':unittest.main()
