"""Source bootstrap contracts without downloading Python or model packages."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from installer import service
from scripts import export_next_source

ROOT = Path(__file__).resolve().parent.parent


class SourceSetupTests(unittest.TestCase):
    def test_app_uses_private_python_for_component_install(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            runtime = data / 'python/python.exe'
            runtime.parent.mkdir()
            runtime.touch()
            with patch.object(service, 'DATA_ROOT', data):
                self.assertEqual(service.python312(), runtime)

    def test_current_export_contains_complete_bootstrap_without_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'source'
            export_next_source.export(output)
            for name in ('kurulum.bat', 'baslat.bat', 'installer/setup_source.ps1',
                         'installer/requirements-ui.txt', 'installer/constraints.txt'):
                self.assertTrue((output / name).is_file(), name)
            self.assertFalse((output / '.venv').exists())
            self.assertFalse((output / '.data').exists())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows bootstrap')
    def test_plan_does_not_create_environment_or_downloads(self):
        # Run a copy: a plan must remain read-only even on a fresh checkout.
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'installer'
            source.mkdir()
            script = source / 'setup_source.ps1'
            script.write_bytes((ROOT / 'installer/setup_source.ps1').read_bytes())
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy',
                'Bypass', '-File', str(script), '-Plan'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((Path(folder) / '.data').exists())
            self.assertFalse((Path(folder) / '.venv').exists())


if __name__ == '__main__':
    unittest.main()
