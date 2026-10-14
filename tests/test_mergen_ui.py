import os
import sys
import unittest
from unittest.mock import Mock, patch

from PIL import Image

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QLabel, QAbstractButton, QComboBox, QGroupBox
from app.config import APP_ICON, Settings
from app.ui.control_panel import ControlPanel
from app.ui.menu_widgets import menu_text
from app.ui.usage_monitor import parse_gpu_usage


class SettingsThemeTests(unittest.TestCase):
    def test_old_panel_theme_names_preserve_selected_appearance(self):
        import json
        with patch('app.config.SETTINGS_FILE') as file:
            file.exists.return_value = True
            for old, new in (('glass_dark', 'green'), ('glass_light', 'white')):
                file.read_text.return_value = json.dumps({'settings_version': 7, 'panel_theme': old, 'theme': 'sepia'})
                loaded = Settings.load()
                self.assertEqual(loaded.panel_theme, new)
                self.assertEqual(loaded.theme, 'sepia')


class MergenUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if sys.platform == "win32":
            from PySide6.QtGui import QFontDatabase
            for font in ("segoeui.ttf", "consola.ttf"):
                QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)

    def setUp(self):
        self.settings = Settings()
        for target, options in (
            ('app.ui.control_panel.Settings.load', {'return_value': self.settings}),
            ('app.ui.control_panel.Settings.save', {}),
            ('app.ui.control_panel.start_global_hotkeys', {'return_value': None}),
            ('app.ui.control_panel.exclude_from_capture', {'return_value': False}),
            ('app.ui.control_panel.OverlayWindow.ensure_platform_setup', {}),
            ('app.ui.usage_monitor.shutil.which', {'return_value': None}),
            ('app.ui.windows_gpu_usage.WindowsGPUUsage', {'side_effect': OSError('disabled in UI tests')}),
        ):
            context = patch(target, **options)
            context.start()
            self.addCleanup(context.stop)
        self.panel = ControlPanel()
        self.panel.show()
        self.app.processEvents()

    def tearDown(self):
        self.panel.settings_dialog.close()
        self.panel.close()

    def test_lowercase_menus_and_full_width_actions(self):
        p = self.panel
        self.assertEqual(p.windowTitle(), 'mergen')
        self.assertFalse(p.windowIcon().isNull())
        self.assertEqual(p.btn_settings.text(), '')
        self.assertFalse(p.btn_settings.icon().isNull())
        self.assertEqual(p.btn_settings.accessibleName(), 'ayarlar')
        p._set_status('OCR: GPU hazır, İngilizce')
        for widget in p.findChildren(QLabel) + p.findChildren(QAbstractButton):
            self.assertEqual(widget.text(), menu_text(widget.text()))
        for widget in p.findChildren(QGroupBox):
            self.assertEqual(widget.title(), menu_text(widget.title()))
        for combo in p.findChildren(QComboBox):
            for i in range(combo.count()):
                self.assertEqual(combo.itemText(i), menu_text(combo.itemText(i)))
        self.assertEqual(p.btn_run.width(), p.width() - 28)
        self.assertEqual(p.btn_now.y(), p.btn_overlay.y())
        self.assertEqual(p.btn_overlay.y(), p.btn_settings.y())
        self.assertGreater(p.btn_settings.x(), p.btn_overlay.x())
        # Original font/model identifiers must retain their exact spelling.
        self.assertEqual(p.cb_font.currentData(), self.settings.font_family)
        self.assertEqual(p.cb_lang.currentData(), self.settings.source_lang)

    def test_compact_layout_and_independent_panel_themes(self):
        p = self.panel
        def top(widget):
            return widget.mapTo(p, widget.rect().topLeft()).y()
        self.assertFalse(p.lbl_region.isVisible())
        self.assertLess(top(p.btn_region), top(p.btn_now))
        self.assertLess(top(p.btn_now), top(p.btn_run))
        self.assertEqual(top(p.btn_region), top(p.btn_full))
        overlay_theme = self.settings.theme
        for theme in ('green', 'white', 'navy', 'black', 'sepia'):
            p.cb_panel_theme.setCurrentIndex(p.cb_panel_theme.findData(theme))
            self.app.processEvents()
            self.assertEqual(self.settings.panel_theme, theme)
            self.assertEqual(self.settings.theme, overlay_theme)
            self.assertGreaterEqual(p.btn_now.width(), p.btn_now.sizeHint().width())

    def test_toolbar_spacing_and_usage_labels_do_not_overlap(self):
        p = self.panel
        buttons = (p.btn_now, p.btn_overlay, p.btn_settings)
        self.assertLessEqual(max(b.width() for b in buttons) - min(b.width() for b in buttons), 1)
        self.assertEqual(buttons[1].x() - buttons[0].geometry().right(),
                         buttons[2].x() - buttons[1].geometry().right())
        for key in ('gpu', 'vram', 'cpu'):
            p.usage_checks[key].setChecked(True)
        p._update_usage({'gpu': 12, 'vram': 73, 'cpu': 28})
        self.app.processEvents()
        for key, value in (('gpu', 12), ('vram', 73), ('cpu', 28)):
            bar = getattr(p, key + '_bar')
            name = p.usage_rows[key].findChild(QLabel, 'usageName')
            number = p.usage_values[key]
            self.assertLess(name.geometry().bottom(), bar.y())
            self.assertLess(number.geometry().bottom(), bar.y())
            self.assertLess(name.geometry().right(), number.x())
            self.assertEqual(p.usage_rows[key].objectName(), 'usageRow')
            self.assertEqual(number.text(), f'{value}%')
            self.assertFalse(bar.isTextVisible())
        p._update_usage({'gpu': None})
        self.assertEqual(p.usage_values['gpu'].text(), 'kullanılamıyor')

    def test_wheel_does_not_change_focused_or_unfocused_combos(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        p = self.panel
        p._show_settings()
        self.app.processEvents()
        for combo in (p.cb_lang, p.cb_panel_theme, p.cb_theme, p.cb_font, p.cb_preset):
            original = combo.currentIndex()
            for focus in (False, True):
                combo.setFocus() if focus else combo.clearFocus()
                event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, -120),
                                    Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                    Qt.ScrollPhase.NoScrollPhase, False)
                self.app.sendEvent(combo, event)
                self.assertEqual(combo.currentIndex(), original)
            if combo.count() > 1:
                combo.setCurrentIndex((original + 1) % combo.count())
                self.assertNotEqual(combo.currentIndex(), original)

    def test_windows_taskbar_icon_contains_native_sizes(self):
        if sys.platform != 'win32':
            self.skipTest('Windows taskbar icon')
        self.assertEqual(APP_ICON.suffix, '.ico')
        with Image.open(APP_ICON) as icon:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)}.issubset(icon.ico.sizes()))
        self.assertFalse(self.panel.windowIcon().isNull())
        self.assertIn((32, 32), {(s.width(), s.height()) for s in self.panel.windowIcon().availableSizes()})

    def test_usage_toggles_restore_individual_choices_and_stop_sampling(self):
        p = self.panel
        p.usage_checks['gpu'].setChecked(True)
        p.usage_checks['vram'].setChecked(True)
        p.usage_checks['cpu'].setChecked(True)
        self.app.processEvents()
        self.assertTrue(all(row.isVisible() for row in p.usage_rows.values()))
        self.assertLess(p.usage_rows['gpu'].y(), p.usage_rows['vram'].y())
        self.assertLess(p.usage_rows['vram'].y(), p.usage_rows['cpu'].y())
        p._update_usage({'gpu': 12, 'vram': 73, 'cpu': 28})
        self.assertEqual((p.gpu_bar.value(), p.vram_bar.value(), p.cpu_bar.value()), (12, 73, 28))
        p.chk_usage.setChecked(False)
        self.assertFalse(p.usage_group.isVisible())
        self.assertFalse(p.usage_monitor.timer.isActive())
        self.assertTrue(self.settings.show_vram_usage)
        p.chk_usage.setChecked(True)
        self.assertTrue(p.usage_rows['vram'].isVisible())
        for checkbox in p.usage_checks.values():
            checkbox.setChecked(False)
        self.assertFalse(p.usage_group.isVisible())
        self.assertFalse(p.usage_monitor.timer.isActive())

    def test_settings_checkboxes_follow_all_selection_controls(self):
        p = self.panel
        p._show_settings()
        self.app.processEvents()
        # The options group follows both appearance and performance groups.
        group = p.chk_visible.parentWidget()
        self.assertGreater(group.y(), p.cb_model.parentWidget().geometry().bottom())
        self.assertGreater(group.y(), p.cb_font.parentWidget().geometry().bottom())

    def test_session_context_toggle_and_reset_use_existing_worker(self):
        p = self.panel
        worker = Mock()
        p.worker = worker
        p.chk_context.setChecked(False)
        self.assertFalse(self.settings.session_context)
        worker.reset_translation_context.assert_called_with(False)
        p.btn_clear_context.click()
        worker.reset_translation_context.assert_called_with()
        self.assertIs(p.worker, worker)
        p.worker = None  # teardown must not treat the mock as a running thread

    def test_gpu_memory_is_capacity_percentage_and_unknown_is_not_zero(self):
        self.assertEqual(parse_gpu_usage('12, 2048, 8192'), {'gpu': 12, 'vram': 25})
        self.assertEqual(parse_gpu_usage('[N/A], 2048, 8192'), {'gpu': None, 'vram': 25})
        self.assertEqual(parse_gpu_usage('12, 0, 0'), {'gpu': 12, 'vram': None})


if __name__ == '__main__':
    unittest.main()
