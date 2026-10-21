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

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl, QPointF, Qt
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
            cancelling=False, canUninstall=False,
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
    def visual_item(parent,name):
        if parent.objectName()==name:return parent
        for child in parent.childItems():
            found=visual_item(child,name)
            if found:return found
    if '--check' not in sys.argv:
        return app.exec()
    output = ROOT.parent / 'tasarimlar' / 'temalar'
    output.mkdir(parents=True, exist_ok=True)
    for theme in ('white', 'black', 'green', 'navy', 'sepia'):
        controller.values['theme'] = theme
        controller.changed.emit()
        QTest.qWait(80)
        rail=window.findChild(QQuickItem,'navigationRail')
        logo=window.findChild(QQuickItem,'railLogo')
        assert rail.width()==72 and logo.width()==32
        assert abs(logo.mapToScene(QPointF(logo.width()/2,0)).x()-rail.width()/2)<1
        for page in range(4):
            nav=visual_item(window.contentItem(),'nav_'+str(page))
            point=nav.mapToScene(QPointF(nav.width()/2,nav.height()/2)).toPoint()
            QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
            QTest.mouseMove(window,QPointF(window.width()-6,6).toPoint())
            QTest.qWait(180)
            assert nav.property('checked')
            if page == 0:
                for usage in (False, True):
                    controller.values.update(showUsage=usage, showGpu=usage, showVram=usage, showCpu=usage)
                    controller.changed.emit()
                    QTest.qWait(100)
                    window.setWidth(window.minimumWidth())
                    window.setHeight(window.minimumHeight())
                    QTest.qWait(100)
                    start = window.findChild(QQuickItem, 'startButton')
                    actions=[window.findChild(QQuickItem,name) for name in (
                        'selectRegionAction','fullScreenAction','translateOnceAction','toggleOverlayAction')]
                    assert max(button.width() for button in actions)-min(button.width() for button in actions)<=1
                    assert all(button.height()==46 for button in actions)
                    assert actions[0].x()==actions[2].x() and actions[1].x()==actions[3].x()
                    assert logo.property('smooth') and logo.property('mipmap')
                    assert logo.property('sourceSize').width()==256
                    assert start.isVisible() and start.height() >= 58
                    bottom = start.mapToScene(QPointF(0, start.height())).y()
                    assert bottom <= window.height() - 35, (bottom, window.height())
                    if usage:
                        panel=window.findChild(QQuickItem,'usagePanel')
                        bottom=panel.mapToScene(QPointF(0,panel.height())).y()
                        assert bottom <= window.height()-44, (theme,bottom,window.height())
                        for key in ('gpu','vram','cpu'):
                            metric=visual_item(window.contentItem(),'usageMetric_'+key)
                            assert metric.isVisible() and metric.width()>60
                        assert window.grabWindow().save(str(output/(theme+'-usage.png')))
                controller.values.update(showUsage=False, showGpu=False, showVram=False, showCpu=False)
                controller.changed.emit()
                QTest.qWait(100)
                assert window.grabWindow().save(str(output / (theme + '.png')))
            if page == 2:
                controller.values.update(busy=True,operationTitle='önerilen bileşenler kuruluyor',
                    phase='model indiriliyor · 412/2460 mib · ortalama 18 mib/sn',progress=17,
                    log='kütüphaneler indirildi.\nmodel dosyaları hazırlanıyor.')
                controller.changed.emit();QTest.qWait(100)
                cancel=window.findChild(QQuickItem,'cancelOperation')
                assert cancel.isVisible() and cancel.isEnabled()
                point=cancel.mapToScene(QPointF(cancel.width(),cancel.height()))
                assert point.x()<=window.width() and point.y()<=window.height()
                assert window.grabWindow().save(str(output/(theme+'-download.png')))
                window.findChild(QQuickItem,'operationPanel').setProperty('logExpanded',True)
                QTest.qWait(100)
                assert window.findChild(QQuickItem,'operationLog').isVisible()
                assert window.grabWindow().save(str(output/(theme+'-download-log.png')))
                window.findChild(QQuickItem,'operationPanel').setProperty('logExpanded',False)
                controller.values.update(busy=False,log='');controller.changed.emit()
        toggle=window.findChild(QQuickItem,'themeToggle')
        point=toggle.mapToScene(QPointF(toggle.width()/2,toggle.height()/2)).toPoint()
        for _ in range(2):
            was_light=controller.values['theme'] in ('white','sepia')
            assert toggle.property('iconName')==('moon' if was_light else 'sun')
            QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
            QTest.qWait(60)
            assert controller.values['theme']==('black' if was_light else 'white')
        QTest.mouseMove(window,QPointF(window.width()-6,6).toPoint())
    if warnings:
        raise AssertionError('\n'.join(warnings))
    window.hide()
    print('QML passed: 5 themes, 4 pages, minimum sizes with usage on/off.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
