import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import config


class UsagePreferencesTests(unittest.TestCase):
    def test_first_launch_and_legacy_defaults_hide_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            with patch.object(config,'SETTINGS_FILE',path):
                self.assertFalse(config.Settings.load().show_gpu_usage)
                path.write_text(json.dumps({'show_gpu_usage':True}),encoding='utf-8')
                loaded=config.Settings.load()
                self.assertFalse(any((loaded.show_gpu_usage,loaded.show_vram_usage,loaded.show_cpu_usage)))

    def test_explicit_usage_choice_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            with patch.object(config,'SETTINGS_FILE',path):
                config.Settings(usage_preferences_set=True,show_cpu_usage=True).save()
                loaded=config.Settings.load()
                self.assertTrue(loaded.show_cpu_usage)
                self.assertFalse(loaded.show_gpu_usage)
