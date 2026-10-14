import re
import tempfile
import unittest
from pathlib import Path

from scripts.bundle_files import bundle_sources, WORKERS
from scripts.export_next_source import source_files


class DistributionSafetyTests(unittest.TestCase):
    def test_bundle_keeps_workers_and_excludes_development_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            for relative in ('app/application.py','installer/apply-update.ps1',
                             *('scripts/'+name for name in WORKERS),
                             'scripts/fetch_build_tools.ps1','scripts/publish_local_copy.ps1',
                             'scripts/create_release_key.py','scripts/test_controller_jobs.py'):
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('test')
            included={p.relative_to(root).as_posix() for p in bundle_sources(root)}
            self.assertIn('app/application.py',included)
            self.assertIn('installer/apply-update.ps1',included)
            self.assertEqual({p for p in included if p.startswith('scripts/')},
                             {'scripts/'+name for name in WORKERS})

    def test_private_key_cannot_enter_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'assets').mkdir()
            (root/'assets/private.pem').write_text('test')
            with self.assertRaises(ValueError):list(bundle_sources(root))

    def test_export_has_no_literal_home_paths_personal_emails_or_secrets(self):
        home=re.compile(r'(?:[A-Za-z]:[/\\]+Users[/\\]+[^/\\\s]+|/home/[A-Za-z0-9_.-]+(?:/|$))',re.I)
        email=re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
        secret=re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b')
        for path in source_files():
            if path.suffix in ('.png','.ico'):continue
            text=path.read_text(encoding='utf-8')
            self.assertFalse(home.search(text),path.name+' contains a literal home path')
            self.assertFalse(secret.search(text),path.name+' contains a private key or token')
            addresses=[v for v in email.findall(text)
                       if not v.endswith('@users.noreply.github.com') and not v.endswith('@example.com')]
            self.assertFalse(addresses,path.name+' contains a personal email address')
