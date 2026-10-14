import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from app.config import Settings
from app.ui.controller import Controller
app=QApplication([])
with patch('app.ui.control_panel.start_global_hotkeys',return_value=None),patch.object(Controller,'refresh'),patch('app.ui.controller.Settings.load',return_value=Settings(check_updates=False)),patch('app.ui.controller.Settings.save'):
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
    controller.monitor.close();controller.stop_hotkeys()
    print('job completion after thread exit; rejected install has no mutation')
