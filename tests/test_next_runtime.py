import base64
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from installer import profiles,service
from app import updates
from app.core.runtime_client import environment_key,RuntimeClient

try:
    import cryptography
except ImportError:
    sys.path.append(str(Path(sys.base_prefix)/'Lib/site-packages'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

class NextTests(unittest.TestCase):
    def test_frozen_cpu_install_supplies_openmp_before_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundle=root/'bundle';bundle.mkdir()
            for name in ('vcomp140.dll','MSVCP140.dll','VCRUNTIME140.dll'):
                (bundle/name).write_bytes(name.encode())
            commands=[]
            def fake_run(args,emit):
                commands.append([str(a) for a in args])
                if args[1:3]==['-m','venv']:
                    (Path(args[3])/'Scripts').mkdir(parents=True)
                else:
                    self.assertTrue((root/'envs/cpu/Scripts/vcomp140.dll').is_file())
            with patch.object(service,'DATA_ROOT',root),patch.object(service,'APP_ROOT',bundle), \
                 patch.object(service.sys,'frozen',True,create=True), \
                 patch.object(service,'python312',return_value=Path('python.exe')), \
                 patch.object(service,'run',side_effect=fake_run), \
                 patch('installer.hardware.detect',return_value={}), \
                 patch('installer.profiles.eligible',return_value=True), \
                 patch.object(service.shutil,'disk_usage',return_value=type('Usage',(),{'free':20*1024**3})()):
                service.install('cpu',lambda _:None)
            self.assertIn('import paddle',commands[-1][-1])
            self.assertTrue((root/'envs/cpu/mergen-ready.json').is_file())

    def report(self,name,build=26100):
        return dict(supported_os=True,avx=True,windows_build=build,adapters=[dict(name=name)],cuda_candidate=False)

    def test_amd_exact_whitelist(self):
        self.assertTrue(profiles.eligible('amd',self.report('AMD Radeon RX 7900 XTX')))
        for name in ('AMD Radeon RX 7900 XT','AMD Radeon RX 7700 XT','AMD Radeon 610M','AMD Radeon RX 9070 Laptop'):
            self.assertFalse(profiles.eligible('amd',self.report(name)))
        self.assertFalse(profiles.eligible('amd',self.report('AMD Radeon RX 9070 XT',19045)))

    def test_supported_ryzen_apu(self):
        report=self.report('AMD Radeon 8060S Graphics');report['processors']=['AMD Ryzen AI MAX+ 395 w/ Radeon 8060S']
        self.assertTrue(profiles.eligible('amd',report))
        report['processors']=['AMD Ryzen 5 7520U']
        self.assertFalse(profiles.eligible('amd',report))

    def test_intel_requires_arc(self):
        self.assertTrue(profiles.eligible('intel',self.report('Intel(R) Arc(TM) B580 Graphics')))
        self.assertFalse(profiles.eligible('intel',self.report('Intel Iris Xe Graphics')))

    def test_cpu_fallback_and_nvidia_plan(self):
        report=self.report('AMD Radeon 610M')
        self.assertEqual(profiles.recommended(report)['translation'],'cpu')
        report['cuda_candidate']=True
        self.assertEqual(profiles.recommended(report)['components'],['cpu','nvidia','600m','ocr-paddle'])

    def test_no_avx_rejected(self):
        report=self.report('NVIDIA');report['avx']=False
        self.assertFalse(profiles.eligible('cpu',report))

    def test_separate_paddle_environment(self):
        self.assertEqual(environment_key('nvidia','ocr'),'nvidia-paddle')
        self.assertEqual(environment_key('amd','ocr'),'amd')

    def test_unknown_runtime_rejected_before_launch(self):
        with patch('app.core.runtime_client.subprocess.Popen') as popen:
            with self.assertRaises(ValueError):RuntimeClient('translate','anything')
            popen.assert_not_called()

    def test_manga_payload_limit(self):
        client=object.__new__(RuntimeClient)
        with self.assertRaises(ValueError):client.recognize([None]*5)

    def test_remove_only_owned_component(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);model=root/'models/manga';model.mkdir(parents=True)
            keep=root/'models/keep';keep.mkdir()
            (model/'weights').write_text('test')
            with patch.object(service,'DATA_ROOT',root):
                service.remove('manga',lambda _:None)
                self.assertFalse(model.exists());self.assertTrue(keep.exists())
                with self.assertRaises(ValueError):service.remove('../keep')

    def test_partial_environment_not_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);env=root/'envs/cpu';env.mkdir(parents=True)
            with patch.object(service,'DATA_ROOT',root):
                self.assertTrue(service.inventory()['cpu']['present'])
                self.assertFalse(service.inventory()['cpu']['ready'])

    def test_untrusted_update_urls(self):
        for url in ('http://github.com/tu5j4/mergen/releases/download/v1/a.exe',
                    'https://github.com.evil/tu5j4/mergen/releases/download/v1/a.exe',
                    'https://github.com/other/mergen/releases/download/v1/a.exe'):
            with self.assertRaises(ValueError):updates.trusted_url(url)

    def test_signed_manifest_and_tampering(self):
        key=Ed25519PrivateKey.generate()
        payload=dict(version='9.0.0',url='https://github.com/tu5j4/mergen/releases/download/v9/a.exe',bytes=4,sha256='0'*64)
        raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        envelope=dict(payload=payload,signature=base64.b64encode(key.sign(raw)).decode())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'assets').mkdir()
            (root/'assets/update-public-key.pem').write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
            with patch.object(updates,'APP_ROOT',root):
                self.assertEqual(updates.verify(envelope),payload)
                tampered=copy.deepcopy(envelope);tampered['payload']['bytes']=5
                with self.assertRaises(Exception):updates.verify(tampered)

    def test_bad_download_hash_never_published(self):
        payload=dict(version='9.0.0',url='https://github.com/tu5j4/mergen/releases/download/v9/a.exe',bytes=4,sha256='0'*64)
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,'DATA_ROOT',Path(folder)),patch('app.updates.urllib.request.urlopen',return_value=io.BytesIO(b'test')):
            with self.assertRaises(ValueError):updates.download_update(payload,lambda _:None)
            self.assertFalse(list(Path(folder).rglob('*.exe')))
            self.assertFalse(list(Path(folder).rglob('*.part')))

    def test_old_update_not_downloaded(self):
        with patch('app.updates.urllib.request.urlopen') as request:
            with self.assertRaises(ValueError):updates.download_update(dict(version='0.1.0'))
            request.assert_not_called()

if __name__=='__main__':unittest.main()
