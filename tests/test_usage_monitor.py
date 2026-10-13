import unittest
from unittest.mock import patch, Mock
from PySide6.QtCore import QCoreApplication
from app.ui.usage_monitor import UsageMonitor
from app.ui.windows_gpu_usage import aggregate_usage


class GPUUsageTests(unittest.TestCase):
    def test_busiest_engine_combines_processes_but_not_different_adapters(self):
        luid = 'luid_0x00000000_0x00001234'
        prefix = 'pid_1_' + luid + '_phys_0_eng_'
        readings = aggregate_usage([
            (prefix + '0_engtype_3D', 14),
            ('pid_2_' + luid + '_phys_0_eng_0_engtype_3D', 18),
            (prefix + '1_engtype_Copy', 20),
            ('pid_3_luid_0x00000000_0x00005678_phys_0_eng_0_engtype_3D', 99),
            (prefix + '2_engtype_Compute', float('nan')),
        ], [(luid + '_phys_0', 250), ('luid_other_phys_0', 900)], luid, 1000)
        self.assertEqual(readings, {'gpu': 32, 'vram': 25})

    def test_missing_counters_are_unknown_and_overload_is_clamped(self):
        self.assertEqual(aggregate_usage([], [], 'luid_a', 0), {'gpu': None, 'vram': None})
        self.assertEqual(aggregate_usage([('luid_a_phys_0_eng_0', 120)],
                                        [('luid_a_phys_0', 1200)], 'luid_a', 1000),
                         {'gpu': 100, 'vram': 100})

    def test_nvml_failure_switches_to_windows_and_releases_query(self):
        app = QCoreApplication.instance() or QCoreApplication([])
        native = Mock(name='native_sampler')
        native.name = 'test GPU'
        native.sample.return_value = {'gpu': 26, 'vram': 61}
        with patch('app.ui.usage_monitor.shutil.which', return_value='nvidia-smi'), \
             patch('app.ui.windows_gpu_usage.WindowsGPUUsage', return_value=native) as create:
            monitor = UsageMonitor()
            monitor.enabled = dict(gpu=True, vram=True, cpu=False)
            received = []
            monitor.readings.connect(received.append)
            monitor._finished(1, None)
            self.assertEqual(received[-1], {'gpu': 26, 'vram': 61})
            self.assertTrue(monitor.source.startswith('windows'))
            monitor.sample()
            create.assert_called_once()
            self.assertEqual(native.sample.call_count, 2)
            monitor.set_enabled(False, False, False)
            monitor.sample()
            self.assertEqual(native.sample.call_count, 2)
            monitor.close()
            native.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
