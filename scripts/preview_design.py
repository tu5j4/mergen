"""Render the real QML with sample state; no models, network or saved settings.

Usage: python scripts/preview_design.py [--check]
This is a design preview, not a working translation controller.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if '--check' in sys.argv:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl, QPointF
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from app.config import Settings
from app.storage import VERSION


class PreviewController(QObject):
    changed = Signal()
    navigate = Signal(int)
    confirmation = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.values = dict(theme='white', language='ja', model='600m',
            translationBackend='cpu', ocrBackend='cpu', mangaBackend='cpu',
            opacity=.93, mangaEnabled=True, fontFamily='Segoe UI', maxFont=40,
            bold=True, preset='balanced', scrollTracking=True, contextEnabled=True,
            chinesePivot=False, checkUpdates=False, showGpu=False, showVram=False,
            showCpu=False, showUsage=False, shareTranslations=True,
            usage=dict(gpu='20%', vram='30%', cpu='12%'), running=False, busy=False,
            version=VERSION, status='Hazır · Tasarım önizlemesi', components=[],
            hardware='Donanım bilgileri burada gösterilir.', recommendation='',
            validation=[], validationSummary='Model testi henüz çalıştırılmadı.',
            operationTitle='Bileşen durumu', phase='İşlem bekleniyor.', log='',
            progress=-1, activeComponent='', dataPath='Yerel veri klasörü',
            updates='Henüz kontrol edilmedi.', updateAvailable=False)

    @Property('QVariantMap', notify=changed)
    def state(self):
        return self.values.copy()

    @Slot(str, 'QVariant')
    def setting(self, key, value):
        mapping = dict(panel_theme='theme', source_lang='language',
            share_translations='shareTranslations', scroll_tracking='scrollTracking')
        self.values[mapping.get(key, key)] = value
        self.changed.emit()

    @Slot(str)
    def action(self, name):
        if name == 'quit':
            QApplication.instance().quit()

    @Slot(str, str)
    def component(self, operation, key):
        pass

    @Slot(bool)
    def confirm(self, accepted):
        pass


def main():
    app = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    controller = PreviewController()
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda rows: warnings.extend(row.toString() for row in rows))
    engine.rootContext().setContextProperty('controller', controller)
    engine.load(QUrl.fromLocalFile(str(ROOT / 'app/ui/qml/Main.qml')))
    if not engine.rootObjects():
        raise RuntimeError('\n'.join(warnings))
    window = engine.rootObjects()[0]
    if '--check' not in sys.argv:
        return app.exec()
    output = ROOT.parent / 'tasarimlar' / 'temalar'
    output.mkdir(parents=True, exist_ok=True)
    for theme in ('white', 'black', 'green', 'navy', 'sepia'):
        controller.values['theme'] = theme
        controller.changed.emit()
        for page in range(4):
            controller.navigate.emit(page)
            QTest.qWait(180)
            if page == 0:
                for usage in (False, True):
                    controller.values.update(showUsage=usage, showGpu=usage)
                    controller.changed.emit()
                    QTest.qWait(100)
                    window.setWidth(window.minimumWidth())
                    window.setHeight(window.minimumHeight())
                    QTest.qWait(100)
                    start = window.findChild(QQuickItem, 'startButton')
                    assert start.isVisible() and start.height() >= 58
                    bottom = start.mapToScene(QPointF(0, start.height())).y()
                    assert bottom <= window.height() - 35, (bottom, window.height())
                controller.values.update(showUsage=False, showGpu=False)
                controller.changed.emit()
                QTest.qWait(100)
                assert window.grabWindow().save(str(output / (theme + '.png')))
    if warnings:
        raise AssertionError('\n'.join(warnings))
    window.hide()
    print('QML passed: 5 themes, 4 pages, minimum sizes with usage on/off.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
