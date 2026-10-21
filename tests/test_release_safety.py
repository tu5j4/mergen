import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from app import updates
from scripts import export_next_source as exporter
from scripts import sign_release_local as signer


class ReleaseSafetyTests(unittest.TestCase):
    def test_private_data_fails_before_any_export_is_written(self):
        for payload in (b'-----BEGIN '+b'PRIVATE KEY-----', b'ghp_'+b'x'*36,
                        b'C:'+bytes([92])+b'Users'+bytes([92])+b'example'+bytes([92])+b'file'):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)/'source'
                root.mkdir()
                for name in exporter.FILES:
                    path=root/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('',encoding='utf-8')
                bad=root/'app/data/accidental.json'
                bad.parent.mkdir(parents=True)
                bad.write_bytes(payload)
                output=Path(folder)/'published'
                with self.assertRaises(ValueError):
                    exporter.export(output,root)
                self.assertFalse(output.exists())

    def test_manifest_is_signed_and_modified_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'assets').mkdir()
            key=Ed25519PrivateKey.generate()
            (root/'assets/update-public-key.pem').write_bytes(key.public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo))
            private=root/'private.pem'
            private.write_bytes(key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
            installer=root/f'mergen-setup-{signer.VERSION}.exe'
            installer.write_bytes(b'test installer')
            with patch.object(signer,'ROOT',root),patch.object(updates,'APP_ROOT',root):
                envelope=signer.sign(installer,private,root/'release','test')
                self.assertEqual(updates.verify(envelope)['bytes'],len(b'test installer'))
                envelope['payload']['notes']='modified'
                with self.assertRaises(Exception):
                    updates.verify(envelope)
            exported={p.name for p in (root/'release').iterdir()}
            self.assertEqual(exported,{'mergen-update.json','SHA256SUMS.txt'})

    def test_wrong_key_cannot_publish_a_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'assets').mkdir()
            (root/'assets/update-public-key.pem').write_bytes(Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo))
            private=root/'private.pem'
            private.write_bytes(Ed25519PrivateKey.generate().private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
            installer=root/f'mergen-setup-{signer.VERSION}.exe'
            installer.write_bytes(b'test')
            with patch.object(signer,'ROOT',root),self.assertRaises(ValueError):
                signer.sign(installer,private,root/'release','test')
            self.assertFalse((root/'release').exists())


if __name__=='__main__':
    unittest.main()
