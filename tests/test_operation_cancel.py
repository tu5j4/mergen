import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import psutil
from app.operations import operation, Cancelled
from app.core.runtime_client import RuntimeClient
from installer import service


class CancellationTests(unittest.TestCase):
    def test_silent_install_child_and_grandchild_are_stopped(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            script=root/'child.py'
            script.write_text('import subprocess,sys,time,json\n'
                'from pathlib import Path\n'
                'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])\n'
                'Path(sys.argv[1]).write_text(json.dumps([__import__("os").getpid(),child.pid]))\n'
                'time.sleep(60)\n',encoding='utf-8')
            token=threading.Event();errors=[]
            def worker():
                try:
                    with operation(token):service.run([sys.executable,script,root/'pids.json'],lambda _:None)
                except Cancelled:errors.append('cancelled')
            with patch.object(service,'DATA_ROOT',root):
                thread=threading.Thread(target=worker);thread.start()
                deadline=time.monotonic()+10
                try:
                    while not (root/'pids.json').exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertTrue((root/'pids.json').exists())
                    pids=json.loads((root/'pids.json').read_text())
                finally:
                    token.set();thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors,['cancelled'])
            self.assertTrue(all(not psutil.pid_exists(pid) for pid in pids),pids)

    def test_cancel_before_start_prevents_process_launch(self):
        token=threading.Event();token.set()
        with patch('subprocess.Popen') as launch:
            with self.assertRaises(Cancelled):
                with operation(token):service.run([sys.executable,'-c','pass'],lambda _:None)
            launch.assert_not_called()

    def test_cancelled_runtime_start_does_not_wait_for_model_timeout(self):
        client=object.__new__(RuntimeClient)
        client.timeout=300;client._responses=queue.Queue()
        token=threading.Event()
        timer=threading.Timer(.1,token.set);timer.start()
        started=time.monotonic()
        try:
            with self.assertRaises(Cancelled):
                with operation(token):client._receive()
        finally:timer.join()
        self.assertLess(time.monotonic()-started,2)

    def test_cancelled_plan_does_not_start_next_component(self):
        token=threading.Event()
        state={key:{'ready':False} for key in ('cpu','600m','ocr-paddle')}
        def install(key,emit):token.set()
        with patch('installer.hardware.detect',return_value={}),patch('installer.profiles.eligible',return_value=True),patch.object(service,'inventory',return_value=state),patch.object(service,'install',side_effect=install) as install_mock:
            with self.assertRaises(Cancelled):
                with operation(token):service.install_plan({'translation':'cpu','components':list(state)},lambda _:None)
        self.assertEqual(install_mock.call_count,1)


if __name__=='__main__':unittest.main()
