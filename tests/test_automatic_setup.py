from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.config import Settings
from app.operations import Cancelled
from installer import service
from installer.catalog import COMPONENTS
from scripts.pack_model_archives import pack
from scripts.restore_packed_models import restore,unshuffle


class AutomaticSetupTests(unittest.TestCase):
    def run_setup(self, backend='nvidia',failure=None,validation_failure=False,cached=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        state={key:dict(ready=False) for key in COMPONENTS}
        for key,item in COMPONENTS.items():
            if item.get('bundled') or cached:state[key]['ready']=True
        installed=[];trials=[]
        def install(key,emit):
            installed.append(key)
            if key==backend and failure:raise failure
            state[key]['ready']=True
        def validate(s,emit):
            trials.append(s)
            ok=not validation_failure or s.translation_backend=='cpu'
            return dict(ok=ok,rows=[dict(task='translate',status='passed' if ok else 'failed')],translation=s.translation_backend)
        with ExitStack() as stack:
            stack.enter_context(patch('installer.hardware.detect',return_value={}))
            stack.enter_context(patch('installer.profiles.eligible',return_value=True))
            stack.enter_context(patch('installer.profiles.recommended',return_value=dict(translation=backend)))
            stack.enter_context(patch.object(service,'DATA_ROOT',Path(temp.name)))
            stack.enter_context(patch.object(service,'inventory',side_effect=lambda:state))
            stack.enter_context(patch.object(service,'install',side_effect=install))
            stack.enter_context(patch.object(service,'validate',side_effect=validate))
            settings=Settings(translation_model='nllb-1.3b-baglam-v3',source_lang='ja',use_manga_ocr=True)
            result=service.automatic_setup(settings,lambda _:None)
        return result,installed,trials,settings

    def test_gpu_install_and_language_settings_preserved(self):
        result,installed,trials,original=self.run_setup()
        self.assertEqual(installed,['cpu','nvidia'])
        self.assertEqual(result['selected_settings'],dict(translation_backend='nvidia',ocr_backend='cpu',manga_backend='nvidia'))
        self.assertEqual(trials[0].translation_model,original.translation_model)
        self.assertTrue(trials[0].use_manga_ocr)
        self.assertEqual(original.translation_backend,'local')

    def test_gpu_download_error_falls_back_to_tested_cpu(self):
        result,_,trials,_=self.run_setup(failure=RuntimeError('download failed'))
        self.assertTrue(result['ok']);self.assertEqual(trials[0].translation_backend,'cpu')
        self.assertTrue(result['fallback_reason'])

    def test_gpu_tensor_success_but_real_model_failure_falls_back(self):
        result,_,trials,_=self.run_setup(validation_failure=True)
        self.assertEqual([s.translation_backend for s in trials],['nvidia','cpu'])
        self.assertTrue(result['ok']);self.assertEqual(result['selected_settings']['manga_backend'],'cpu')
        self.assertFalse(result['initial_gpu_test']['ok'])

    def test_cancel_does_not_trigger_cpu_fallback(self):
        with self.assertRaises(Cancelled):self.run_setup(failure=Cancelled())

    def test_cpu_only_does_not_download_gpu_runtime(self):
        result,installed,_,_=self.run_setup(backend='cpu')
        self.assertEqual(installed,['cpu']);self.assertTrue(result['ok'])

    def test_existing_runtimes_are_tested_without_reinstalling(self):
        result,installed,trials,_=self.run_setup(cached=True)
        self.assertEqual(installed,[]);self.assertEqual(len(trials),1);self.assertTrue(result['ok'])

    def test_cpu_install_failure_is_not_reported_as_success(self):
        with self.assertRaises(RuntimeError):self.run_setup(backend='cpu',failure=RuntimeError('offline'))


class PackedModelTests(unittest.TestCase):
    def test_round_trip_including_odd_lengths_and_multiple_streams(self):
        for width in (2,4):
            with tempfile.TemporaryDirectory() as folder:
                # Match the installer entry point, which resolves its data root.
                # GitHub's Windows TEMP may otherwise use a RUNNER~1 alias.
                root=Path(folder).resolve();src=root/'original';data=bytes(range(251))*55+b'!'
                src.write_bytes(data);archive=root/'model-archives/test.xz';archive.parent.mkdir()
                hashed=pack(src,archive,width,workers=2,chunk=512)
                row=dict(path='models/weights.bin',archive='test.xz',width=width,chunk=512,bytes=len(data),sha256=hashed,
                    archive_bytes=archive.stat().st_size,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
                target=root/row['path'];target.parent.mkdir();target.write_bytes(b'old model')
                restore(root,dict(schema=1,format='byte-lanes-xz-streams',files=[row]),lambda _:None)
                self.assertEqual(target.read_bytes(),data);self.assertFalse(archive.exists())

    def test_bad_output_hash_preserves_existing_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();src=root/'original';src.write_bytes(b'new model data')
            archive=root/'model-archives/test.xz';archive.parent.mkdir();pack(src,archive,4,workers=1,chunk=8)
            row=dict(path='models/weights.bin',archive='test.xz',width=4,chunk=8,bytes=src.stat().st_size,sha256='0'*64,
                archive_bytes=archive.stat().st_size,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
            target=root/row['path'];target.parent.mkdir();target.write_bytes(b'original weights')
            with self.assertRaises(ValueError):restore(root,dict(schema=1,format='byte-lanes-xz-streams',files=[row]),lambda _:None)
            self.assertEqual(target.read_bytes(),b'original weights')
            self.assertFalse(list(target.parent.glob('*.restore-*')))

    def test_archive_path_traversal_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as folder:
            row=dict(path='models/weights',archive='../outside',width=4,chunk=512,bytes=1)
            with self.assertRaises(ValueError):restore(Path(folder),dict(schema=1,format='byte-lanes-xz-streams',files=[row]))


if __name__=='__main__':unittest.main()
