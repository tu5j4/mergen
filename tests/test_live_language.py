import copy
import os
import time
import unittest
from unittest.mock import Mock,patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
from PySide6.QtCore import Qt,QPointF,QUrl,QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.config import Settings
from app.storage import APP_ROOT
from app.ui.next_controller import Controller


class LiveLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')

    def setUp(self):
        initial=Settings(check_updates=False,source_lang='en')
        self.patches=[patch.object(Controller,'refresh'),patch('app.ui.next_controller.Settings.load',side_effect=lambda:copy.deepcopy(initial)),
            patch('app.ui.next_controller.Settings.save'),patch('app.ui.control_panel.start_global_hotkeys',return_value=None)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.c=Controller()

    def tearDown(self):
        if self.c.job:
            self.c.cancel_job()
            deadline=time.monotonic()+3
            while self.c.job and time.monotonic()<deadline:QTest.qWait(10)
        self.c.release_backend();self.c.stop_hotkeys();self.c.monitor.close()
        self.app.processEvents()

    def test_running_language_switch_reuses_models_and_region(self):
        b=self.c.ensure_backend();b.worker=Mock();b.running=True;self.c._state['running']=True
        b.region=object();region=b.region
        self.c.setting('source_lang','ko')
        self.assertIs(self.c.backend,b);self.assertIs(b.region,region)
        self.assertTrue(b.running);self.assertTrue(self.c.state['running'])
        self.assertEqual(self.c.settings.source_lang,'ko');self.assertEqual(b.s.source_lang,'ko')
        b.worker.set_language.assert_called_once_with('ko')

    def test_idle_backend_is_not_stopped_to_change_language(self):
        b=self.c.ensure_backend();b.worker=Mock()
        self.c.setting('source_lang','ja')
        self.assertIs(self.c.backend,b)
        self.assertFalse(self.c._stopping)
        b.worker.stop.assert_not_called();b.worker.set_language.assert_called_once_with('ja')

    def test_read_only_scan_does_not_lock_language_or_busy_state(self):
        self.c.start_job(lambda emit:time.sleep(.2),read_only=True)
        self.assertFalse(self.c.state['busy']);self.assertTrue(self.c.state['languageSelectable'])
        self.assertFalse(self.c.state['operationAvailable'])
        self.c.setting('source_lang','zh_tw')
        self.assertEqual(self.c.settings.source_lang,'zh_tw')

    def test_dependency_job_still_blocks_language_changes(self):
        self.c.start_job(lambda emit:time.sleep(.2))
        self.assertFalse(self.c.state['languageSelectable'])
        self.c.setting('source_lang','ko')
        self.assertEqual(self.c.settings.source_lang,'en')

    def test_mouse_selects_all_languages_during_translation(self):
        b=self.c.ensure_backend();b.worker=Mock();b.running=True;self.c._state['running']=True
        engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('controller',self.c)
        engine.load(QUrl.fromLocalFile(str(APP_ROOT/'app/ui/qml/Main.qml')))
        self.assertTrue(engine.rootObjects());window=engine.rootObjects()[0];QTest.qWait(80)
        combo=window.findChild(QQuickItem,'languageSelect')
        pulses=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:pulses.append(time.monotonic()));timer.start()
        for index,language in enumerate(('ja','ko','zh','zh_tw','en')):
            center=combo.mapToScene(QPointF(combo.width()/2,combo.height()/2)).toPoint()
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,center);QTest.qWait(15)
            row=combo.mapToScene(QPointF(60,combo.height()+12+42*index+21)).toPoint()
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,row);QTest.qWait(15)
            self.assertEqual(self.c.settings.source_lang,language)
            self.assertEqual(b.s.source_lang,language)
        timer.stop();self.assertGreater(len(pulses),10)
        self.assertIs(self.c.backend,b);b.worker.stop.assert_not_called()
        window.hide();engine.rootContext().setContextProperty('controller',self.c)


if __name__=='__main__':unittest.main()
