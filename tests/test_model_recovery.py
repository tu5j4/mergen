import contextlib
import json
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.core.runtime_client import RuntimeClient
from installer import service
from scripts import component_models as models


class ModelRecoveryTests(unittest.TestCase):
    def test_failed_download_is_retained_and_reused_without_publishing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def interrupted(repo,path,**kwargs):
                path.mkdir(parents=True,exist_ok=True)
                (path/'partial').write_bytes(b'reusable download')
                raise ConnectionError('interrupted')
            with patch.object(models,'DATA_ROOT',root),patch.object(models,'model_lock',return_value=contextlib.nullcontext()),patch.object(models,'download',side_effect=interrupted):
                with self.assertRaises(ConnectionError):models.install_model('manga')
            partial=root/'cache/model-downloads/manga/manga/partial'
            self.assertTrue(partial.exists())
            self.assertFalse((root/'models/manga').exists())
            def resume(repo,path,**kwargs):
                self.assertTrue((path/'partial').exists())
                for name in ('pytorch_model.bin','config.json','vocab.txt','preprocessor_config.json'):
                    (path/name).write_bytes(b'test')
            with patch.object(models,'DATA_ROOT',root),patch.object(models,'model_lock',return_value=contextlib.nullcontext()),patch.object(models,'download',side_effect=resume):
                models.install_model('manga')
            self.assertTrue((root/'models/manga/mergen-ready.json').is_file())
            self.assertFalse((root/'cache/model-downloads/manga').exists())

    def test_partial_cache_is_visible_and_removal_is_component_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for key in ('manga','600m'):
                (root/'cache/model-downloads'/key).mkdir(parents=True)
            with patch.object(service,'DATA_ROOT',root):
                self.assertTrue(service.inventory()['manga']['present'])
                self.assertFalse(service.inventory()['manga']['ready'])
                service.remove('manga',lambda _:None)
            self.assertFalse((root/'cache/model-downloads/manga').exists())
            self.assertTrue((root/'cache/model-downloads/600m').exists())

    def test_invalid_model_cannot_receive_ready_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def invalid(repo,path,**kwargs):path.mkdir(parents=True,exist_ok=True)
            with patch.object(models,'DATA_ROOT',root),patch.object(models,'model_lock',return_value=contextlib.nullcontext()),patch.object(models,'download',side_effect=invalid):
                with self.assertRaises(RuntimeError):models.install_model('manga')
            self.assertFalse(list(root.rglob('mergen-ready.json')))

    def test_runtime_progress_is_delivered_before_ready(self):
        client=object.__new__(RuntimeClient)
        client.timeout=180;client._responses=queue.Queue()
        phases=[];client._progress=phases.append
        client._responses.put({'event':'progress','phase':'ocr yükleniyor'})
        client._responses.put({'ok':True,'device':'cpu'})
        self.assertEqual(client._receive(timeout=.1)['device'],'cpu')
        self.assertEqual(phases,['ocr yükleniyor'])
        self.assertEqual(client.timeout,180)

    def test_progress_does_not_reset_startup_deadline(self):
        client=object.__new__(RuntimeClient)
        client.timeout=180;client._progress=None
        client._responses=unittest.mock.Mock()
        client._responses.get.side_effect=[{'event':'progress','phase':'ocr yükleniyor'},queue.Empty()]
        with patch('app.core.runtime_client.time.monotonic',side_effect=[10,10,10.5,11]):
            with self.assertRaisesRegex(TimeoutError,'ocr yükleniyor'):
                client._receive(timeout=1)
        self.assertEqual(client._responses.get.call_args_list[0].kwargs['timeout'],.1)
        self.assertEqual(client._responses.get.call_args_list[1].kwargs['timeout'],.1)


if __name__=='__main__':unittest.main()
