"""Updates must verify TLS even when Windows has no populated root store."""
import io
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import updates

class UpdateTlsTests(unittest.TestCase):
    def test_bundled_roots_work_without_system_roots(self):
        empty=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(empty.cert_store_stats()['x509_ca'],0)
        with patch.object(updates.ssl,'create_default_context',return_value=empty):
            context=updates.tls_context()
        self.assertGreater(context.cert_store_stats()['x509_ca'],100)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_release_requests_verify_tls(self):
        with patch.object(updates.urllib.request,'urlopen',return_value=io.BytesIO(b'{}')) as opened:
            self.assertEqual(updates.request_json('https://api.github.com/repos/tu5j4/mergen/releases/latest'),{})
        context=opened.call_args.kwargs['context']
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_installer_download_verifies_tls_and_hash(self):
        import hashlib
        payload=dict(version='9.0.0',url='https://github.com/tu5j4/mergen/releases/download/v9/a.exe',
                     bytes=4,sha256=hashlib.sha256(b'test').hexdigest())
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,'DATA_ROOT',Path(folder)),patch.object(updates.urllib.request,'urlopen',return_value=io.BytesIO(b'test')) as opened:
            result=updates.download_update(payload,lambda _:None)
            self.assertEqual(Path(result['installer']).read_bytes(),b'test')
        context=opened.call_args.kwargs['context']
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
