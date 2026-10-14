import os,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
os.environ['QT_QUICK_CONTROLS_STYLE']='Basic'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtQuick import QQuickWindow,QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl,QMetaObject,Qt,QObject,QPointF
from unittest.mock import patch
from app.config import Settings
from app.storage import APP_ROOT
from app.ui.controller import Controller
app=QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
with patch('app.ui.control_panel.start_global_hotkeys',return_value=None),patch.object(Controller,'refresh'),patch('app.ui.controller.Settings.load',return_value=Settings(check_updates=False)),patch('app.ui.controller.Settings.save'):
    controller=Controller()
    controller._state['components']=[dict(key=k,ready=False,present=False,title=v['title'],detail=v['detail']) for k,v in __import__('installer.catalog',fromlist=['COMPONENTS']).COMPONENTS.items()]
    engine=QQmlApplicationEngine();engine.warnings.connect(lambda warnings:print('\n'.join(w.toString() for w in warnings),flush=True));engine.rootContext().setContextProperty('controller',controller)
    engine.load(QUrl.fromLocalFile(str(APP_ROOT/'app/ui/qml/Main.qml')))
    assert engine.rootObjects(),'QML failed to load'
    window=engine.rootObjects()[0]
    for i in range(10):app.processEvents();time.sleep(.03)
    print('window',window.width(),window.height())
    assert window.grabWindow().save(str(APP_ROOT/'qml-preview.png'))
    for theme in ('green','white','navy','black','sepia'):
        controller.settings.panel_theme=theme;controller.changed.emit()
        for tab in (0,1,2,3):
            controller.navigate.emit(tab)
            for _ in range(3):app.processEvents()
            QTest.qWait(150)
            assert window.grabWindow().save(str(APP_ROOT/f'preview-{theme}-{tab}.png'))
            if tab==1:
                select=window.findChild(QQuickItem,'themeSelect')
                point=select.mapToScene(QPointF(select.width()/2,select.height()/2)).toPoint()
                QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
                for _ in range(3):app.processEvents()
                assert window.grabWindow().save(str(APP_ROOT/f'preview-{theme}-popup.png'))
                QTest.keyClick(window,Qt.Key.Key_Escape)
                app.processEvents()
    controller.settings.show_gpu_usage=False;controller.settings.show_vram_usage=False;controller.settings.show_cpu_usage=False
    controller.changed.emit();controller.navigate.emit(0)
    for _ in range(5):app.processEvents()
    panel=window.findChild(__import__('PySide6.QtCore',fromlist=['QObject']).QObject,'usagePanel')
    assert panel and not panel.property('visible'),'empty usage panel must disappear'
    assert window.height()<500,'returning to main with no usage must compact window'
    # Native resize must stop below the full primary control group. Test at the
    # advertised minimum size, both with the usage panel hidden and enabled.
    start=window.findChild(QQuickItem,'startButton')
    for usage in (False,True):
        controller.setting('show_gpu_usage',usage)
        for _ in range(5):app.processEvents()
        window.setWidth(window.minimumWidth());window.setHeight(window.minimumHeight())
        for _ in range(5):app.processEvents()
        bottom=start.mapToScene(QPointF(0,start.height())).y()
        assert start.isVisible() and bottom <= window.height()-35,(bottom,window.height())
        assert start.height()>=58,'start action must never shrink or scroll away'
        assert window.grabWindow().save(str(APP_ROOT/f'preview-minimum-usage-{usage}.png'))
    window.setHeight(window.minimumHeight()+180)
    for _ in range(5):app.processEvents()
    assert panel.property('visible')
    assert window.grabWindow().save(str(APP_ROOT/'preview-usage-expanded.png'))
    window.hide();controller.stop_hotkeys();controller.monitor.close()
