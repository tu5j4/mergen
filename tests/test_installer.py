import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch, Mock

from installer.hardware import cuda_eligible, vendor
from installer.manager import COMPONENTS, CORE_PACKAGES, Manager, owned_path, wizard
from scripts.build_distribution import build, source_files, ROOT


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hardware = dict(cuda_candidate=True, supported_os=True,
                             supported_python=True, avx=True, vc_runtime=True,
                             free_gib=100)
        self.manager = Manager(self.root, hardware=self.hardware)
        self.inventory = dict(ready={k: False for k in COMPONENTS}, versions={})

    def test_vendors(self):
        for name, expected in [('AMD Radeon 610M', 'amd'), ('Intel Arc', 'intel'),
                               ('NVIDIA GeForce', 'nvidia'), ('virtual', 'bilinmiyor')]:
            self.assertEqual(vendor(name), expected)

    def test_cuda_requires_known_driver_and_architecture(self):
        self.assertTrue(cuda_eligible(dict(driver='576.02', compute_capability='7.5')))
        for driver, capability in [('575.99', '8.6'), ('617.14', '6.1'),
                                   ('617.14', '13.0'), ('N/A', '12.0')]:
            self.assertFalse(cuda_eligible(dict(driver=driver, compute_capability=capability)))
        self.assertFalse(cuda_eligible({}))

    def test_dependency_plan(self):
        self.assertEqual(self.manager.plan(['korean'], self.inventory), ['core', 'paddle-cpu', 'korean'])
        self.inventory['ready']['core'] = True
        self.inventory['ready']['paddle-gpu'] = True
        self.assertEqual(self.manager.plan(['korean'], self.inventory), ['korean'])

    def test_invalid_or_conflicting_selections(self):
        for selected in [['paddle-cpu', 'paddle-gpu'], ['arbitrary-package']]:
            with self.assertRaises(ValueError):
                self.manager.plan(selected, self.inventory)
        self.hardware['cuda_candidate'] = False
        with self.assertRaises(ValueError):
            self.manager.plan(['manga-gpu'], self.inventory)

    def test_declined_install_has_no_writes(self):
        with patch.object(self.manager, 'scan', return_value=self.inventory), \
             patch('installer.manager.confirm', return_value=False), \
             patch.object(self.manager, 'run') as run:
            self.manager.install(['paddle-cpu', '600m'])
        run.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_interactive_wizard_keeps_selected_components(self):
        self.hardware['cuda_candidate'] = False
        with patch('builtins.input', side_effect=['e', '1', '1']), \
             patch.object(self.manager, 'install') as install:
            wizard(self.manager)
        install.assert_called_once_with(['core', 'paddle-cpu', 'korean', 'manga-cpu', '600m'])

    def test_declined_remove_preserves_files(self):
        marker = self.root / 'settings.json'
        marker.write_text('{}')
        with patch('installer.manager.confirm', return_value=False):
            self.manager.remove(['core'])
        self.assertTrue(marker.exists())
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_paths_reject_root_and_escape(self):
        for relative in ['.', '..', '../other', str(self.root)]:
            with self.assertRaises(ValueError):
                owned_path(self.root, relative)
        self.assertEqual(owned_path(self.root, 'models/test'), self.root / 'models/test')

    def test_remove_validates_all_paths_before_deleting(self):
        keep = self.root / 'keep'
        keep.mkdir()
        with self.assertRaises(ValueError):
            self.manager.remove_paths(['keep', '../outside'])
        self.assertTrue(keep.exists())

    def test_link_cannot_escape(self):
        link = self.root / 'link'
        try:
            link.symlink_to(self.root.parent, target_is_directory=True)
        except OSError:
            if sys.platform != 'win32':
                raise
            # NTFS junctions exercise the same reparse-point protection without
            # requiring Developer Mode or changing the user's security policy.
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                "New-Item -ItemType Junction -Path '" + str(link).replace("'", "''")
                + "' -Target '" + str(self.root.parent).replace("'", "''") + "' | Out-Null"], check=True)
        try:
            with self.assertRaises(ValueError):
                owned_path(self.root, 'link/models')
        finally:
            if link.is_symlink():
                link.unlink()
            else:
                link.rmdir()  # Remove only the junction, never its target.

    def test_model_removal_only_affects_selected_copy(self):
        selected = self.root / 'models/nllb-200-distilled-600M-ct2'
        other = self.root / 'models/nllb-200-distilled-1.3B-ct2'
        for folder in [selected, other]:
            folder.mkdir(parents=True)
            (folder / 'model.bin').write_bytes(b'test')
        with patch('installer.manager.confirm', return_value=True):
            self.manager.remove(['600m'])
        self.assertFalse(selected.exists())
        self.assertTrue((other / 'model.bin').exists())
        settings = json.loads((self.root / 'settings.json').read_text())
        self.assertEqual(settings['translation_model'], other.name)

    def test_legacy_shared_cache_is_not_removed(self):
        with patch('installer.manager.confirm', return_value=True), \
             patch.object(self.manager, 'remove_paths') as remove:
            with self.assertRaises(RuntimeError):
                self.manager.remove(['korean'])
        remove.assert_not_called()

    def test_managed_cache_environment(self):
        (self.root / '.mergen-managed').write_text('1')
        manager = Manager(self.root, hardware=self.hardware)
        self.assertEqual(manager.env['HF_HOME'], str(self.root / '.cache/huggingface'))
        self.assertEqual(manager.env['PADDLE_PDX_CACHE_HOME'], str(self.root / '.cache/paddlex'))

    def test_fresh_copy_ignores_development_shared_cache(self):
        self.assertEqual(self.manager.env['HF_HOME'], str(self.root / '.cache/huggingface'))
        fake_home = self.root / 'other-user-cache'
        for name in ['korean_PP-OCRv5_mobile_rec']:
            folder = fake_home / '.paddlex/official_models' / name
            folder.mkdir(parents=True)
            (folder / 'inference.json').write_text('{}')
            (folder / 'inference.pdiparams').write_bytes(b'model')
        with patch('installer.manager.Path.home', return_value=fake_home), \
             patch('installer.manager.package_versions', return_value={}):
            self.assertFalse(self.manager.scan()['ready']['korean'])

    def test_backend_replacement_removes_both_before_install(self):
        calls = Mock()
        with patch.object(self.manager, 'pip', calls.pip), \
             patch.object(self.manager, 'install_packages', calls.install), \
             patch.object(self.manager, 'run'), patch.object(self.manager, 'download'), \
             patch.object(self.manager, 'write_settings'):
            self.manager.install_one('paddle-cpu')
        self.assertEqual(calls.mock_calls[0].args, ('uninstall', '-y', 'paddlepaddle', 'paddlepaddle-gpu'))
        self.assertEqual(calls.mock_calls[1].args, ('paddlepaddle==3.3.1',))

    def test_scan_does_not_mark_partial_models_ready(self):
        (self.root / '.mergen-managed').write_text('1')
        folder = self.root / 'models/nllb-200-distilled-600M-ct2'
        folder.mkdir(parents=True)
        (folder / 'model.bin').write_bytes(b'partial')
        with patch('installer.manager.package_versions', return_value={}):
            report = self.manager.scan()
        self.assertFalse(report['ready']['600m'])

    def test_settings_update_preserves_preferences(self):
        self.manager.write_settings(theme='sepia', region=[10, 20, 30, 40])
        self.manager.write_settings(use_gpu='no')
        settings = json.loads((self.root / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual(settings['theme'], 'sepia')
        self.assertEqual(settings['region'], [10, 20, 30, 40])

    def test_missing_core_health_does_not_install(self):
        with patch.object(self.manager, 'scan', return_value=self.inventory), \
             patch.object(self.manager, 'run') as run:
            self.assertFalse(self.manager.health())
        run.assert_not_called()

    def test_clean_distribution_and_no_overwrite(self):
        output = build(self.root / 'release')
        files = [p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()]
        for forbidden in ['.venv/', '.manga-venv/', '.cache/', 'models/', 'settings.json', '__pycache__', '.env']:
            self.assertFalse(any(forbidden in name for name in files), forbidden)
        self.assertTrue((output / 'github/LICENSE').exists())
        self.assertEqual((output / 'github/app/data/session_terms.json').read_bytes(),
                         (ROOT / 'app/data/session_terms.json').read_bytes())
        self.assertEqual((output / 'kolay-kurulum/program/app/data/session_terms.json').read_bytes(),
                         (ROOT / 'app/data/session_terms.json').read_bytes())
        self.assertTrue((output / 'kolay-kurulum/program/app/core/session_context.py').exists())
        self.assertEqual((output / 'kolay-kurulum/program/assets/mergen-logo.png').read_bytes(), (ROOT / 'assets/mergen-logo.png').read_bytes())
        self.assertEqual((output / 'kolay-kurulum/program/assets/mergen.ico').read_bytes(),
                         (ROOT / 'assets/mergen.ico').read_bytes())
        self.assertEqual((output / 'github/assets/mergen.ico').read_bytes(),
                         (ROOT / 'assets/mergen.ico').read_bytes())
        self.assertTrue((output / 'kolay-kurulum/program/app/launch_gui.py').exists())
        launch = (output / 'kolay-kurulum/baslat.bat').read_text()
        self.assertIn('pythonw.exe', launch)
        self.assertIn('-m app.launch_gui', launch)
        self.assertIn('%~dp0program\\.venv', launch)
        self.assertEqual({p.name for p in (output / 'kolay-kurulum').iterdir()},
                         {'program', 'kurulum.bat', 'baslat.bat', 'bagliliklar.bat', 'beni-oku.txt'})
        self.assertFalse((output / 'kolay-kurulum/program/tests').exists())
        self.assertIn('%~dp0program\\installer', (output / 'kolay-kurulum/kurulum.bat').read_text())
        with self.assertRaises(FileExistsError):
            build(output)


if __name__ == '__main__':
    unittest.main()
