import sys,time,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from app.config import Settings
from app.ui.next_controller import Controller
app=QApplication([])
with patch('app.ui.control_panel.start_global_hotkeys',return_value=None),patch.object(Controller,'refresh'),patch('app.ui.next_controller.Settings.load',return_value=Settings(check_updates=False)),patch('app.ui.next_controller.Settings.save'):
    controller=Controller()
    completed=[]
    controller.start_job(lambda emit:42,lambda value:completed.append((value,controller.job is None)))
    deadline=time.monotonic()+5
    while not completed and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert completed==[(42,True)],completed
    with patch('installer.service.install') as install:
        controller.component('install','cpu');controller.confirm(False);app.processEvents()
        install.assert_not_called()
    controller.validation_done({'ok':False,'rows':[{'task':'translate','status':'missing','title':'çeviri','message':'eksik'}]})
    assert 'hazır' not in controller.state['validationSummary']
    controller.settings.show_gpu_usage=False;controller.settings.show_vram_usage=False;controller.settings.show_cpu_usage=False
    assert not controller.state['showUsage']
    controller.setting('show_cpu_usage',True)
    assert controller.state['showUsage']
    pages=[];controller.navigate.connect(pages.append)
    with patch.object(controller,'release_backend'):
        controller.action('validate')
    assert pages==[2],pages
    # Cancellation interrupts a silent installer subprocess without a UI freeze.
    from installer import service
    started=threading.Event();successful=[]
    def slow_install(emit):
        started.set()
        service.run([sys.executable,'-c','import time;time.sleep(60)'],emit)
    controller.start_job(slow_install,lambda result:successful.append(result))
    assert started.wait(3)
    controller.action('cancel')
    deadline=time.monotonic()+10
    while controller.job is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert controller.job is None
    assert not successful
    assert not controller.state['busy']
    assert controller.state['operationTitle']=='işlemden vazgeçildi'
    # Window close queues exit until the job has actually stopped.
    started.clear()
    controller.start_job(slow_install,lambda result:successful.append(result))
    assert started.wait(3)
    with patch.object(controller,'finish_exit') as exit_app:
        controller.action('quit')
        exit_app.assert_not_called()
        deadline=time.monotonic()+10
        while controller.job is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
        assert controller.job is None
        exit_app.assert_called_once()
    assert not successful
    controller._exit_action=None
    # Rejecting removal cannot launch the uninstaller.
    with patch('app.ui.next_controller.sys.frozen',True,create=True),patch('pathlib.Path.is_file',return_value=True),patch.object(controller,'finish_exit') as exit_app:
        controller.action('uninstall');controller.confirm(False)
        exit_app.assert_not_called()
        controller.action('uninstall');controller.confirm(True)
        assert controller._exit_action=='uninstall'
        exit_app.assert_called_once()
    controller.monitor.close();controller.stop_hotkeys()
    print('job completion after thread exit; rejected install has no mutation')
