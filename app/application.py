"""QML entry point; no model framework is imported at startup."""
import os
import sys
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QIcon, QGuiApplication
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication
from app.storage import APP_ROOT, DATA_ROOT, prepare_data


def main():
    smoke='--smoke-test' in sys.argv
    if smoke:os.environ['QT_QPA_PLATFORM']='offscreen'
    if smoke or '--software' in sys.argv: os.environ['QT_QUICK_BACKEND']='software'
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','Basic')
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app=QApplication(sys.argv)
    app.setApplicationName('mergen');app.setOrganizationName('mergen')
    app.setWindowIcon(QIcon(str(APP_ROOT/'assets/mergen.ico')))
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('mergen.desktop')
    prepare_data()
    from app.ui.controller import Controller
    if smoke:
        from unittest.mock import patch
        with patch.object(Controller,'refresh'),patch('app.ui.control_panel.start_global_hotkeys',return_value=None):controller=Controller()
        controller.settings.check_updates=False
    else:controller=Controller()
    engine=QQmlApplicationEngine()
    engine.rootContext().setContextProperty('controller',controller)
    engine.load(QUrl.fromLocalFile(str(APP_ROOT/'app/ui/qml/Main.qml')))
    if not engine.rootObjects(): return 1
    from app.platform_utils import exclude_from_capture
    QTimer.singleShot(0,lambda:exclude_from_capture(engine.rootObjects()[0]))
    app.aboutToQuit.connect(controller.monitor.close)
    if smoke:
        def finish():
            import json
            window=engine.rootObjects()[0]
            window.grabWindow().save(str(DATA_ROOT/'packaged-preview.png'))
            (DATA_ROOT/'smoke-result.json').write_text(json.dumps({'qml':True,'version':controller.state['version'],
                'model_frameworks_loaded':[n for n in ('torch','paddle','transformers','ctranslate2') if n in sys.modules]}))
            controller.monitor.close();app.quit()
        if '--runtime-test' in sys.argv:
            from dataclasses import replace
            from installer import service
            settings=replace(controller.settings,translation_backend='cpu',ocr_backend='cpu',manga_backend='cpu',source_lang='ja',use_manga_ocr=True)
            def tested(report):
                import json
                (DATA_ROOT/'packaged-runtime-result.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
                finish()
            QTimer.singleShot(1000,lambda:controller.start_job(lambda emit:service.validate(settings,emit),tested))
        else:QTimer.singleShot(1000,finish)
    return app.exec()

if __name__=='__main__':sys.exit(main())
