"""Cooperative background-job cancellation with owned subprocess cleanup."""
import threading
from contextlib import contextmanager


class Cancelled(Exception):
    pass


_local = threading.local()


def check_cancelled():
    token = getattr(_local, 'token', None)
    if token is not None and token.is_set():
        raise Cancelled('işlemden vazgeçildi.')


def kill_tree(process):
    import psutil
    if process.poll() is not None:
        return
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:
        children = []
    for child in reversed(children):
        try: child.kill()
        except psutil.Error: pass
    if process.poll() is None:
        try: process.kill()
        except OSError: pass
    process.wait(timeout=10)
    psutil.wait_procs(children, timeout=5)


def own_process(process):
    processes = getattr(_local, 'processes', None)
    if processes is not None:
        processes.append(process)
    return process


@contextmanager
def operation(token):
    _local.token, _local.processes = token, []
    try:
        check_cancelled()
        yield
        check_cancelled()
    finally:
        try:
            for process in _local.processes:
                kill_tree(process)
        finally:
            del _local.token, _local.processes
