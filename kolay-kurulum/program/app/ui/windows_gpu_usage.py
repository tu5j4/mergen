"""Windows GPU counters used when NVIDIA's NVML interface is unavailable.

PDH supplies WDDM engine load and dedicated memory usage. DXGI supplies the
matching adapter LUID and physical VRAM capacity; counters from other adapters
are never combined with it. No driver changes or extra packages are needed.
"""
import ctypes as C
from ctypes import wintypes as W
import math
import re
import sys
import uuid


def aggregate_usage(engines, memory, luid, capacity):
    totals = {}
    for name, value in engines:
        if luid not in name.lower() or not math.isfinite(value):
            continue
        engine = re.search(r'_phys_(\d+)_eng_(\d+)', name)
        if engine:
            key = engine.groups()
            totals[key] = totals.get(key, 0.0) + max(0.0, value)
    used = [v for name, v in memory if luid in name.lower() and math.isfinite(v) and v >= 0]
    return {
        'gpu': min(100, round(max(totals.values()))) if totals else None,
        'vram': min(100, round(100 * sum(used) / capacity)) if used and capacity > 0 else None,
    }


class _LUID(C.Structure):
    _fields_ = [('low', W.DWORD), ('high', W.LONG)]


class _Desc(C.Structure):
    _fields_ = [('name', W.WCHAR * 128), ('vendor', W.UINT), ('device', W.UINT),
                ('subsys', W.UINT), ('revision', W.UINT), ('dedicated', C.c_size_t),
                ('system', C.c_size_t), ('shared', C.c_size_t), ('luid', _LUID), ('flags', W.UINT)]


class _Number(C.Union):
    _fields_ = [('double', C.c_double), ('large', C.c_longlong), ('long', W.LONG)]


class _Value(C.Structure):
    _anonymous_ = ('number',)
    _fields_ = [('status', W.DWORD), ('number', _Number)]


class _Item(C.Structure):
    _fields_ = [('name', W.LPWSTR), ('value', _Value)]


def _method(obj, index, result, *args):
    table = C.cast(obj, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *args)(table[index])


def _adapter():
    factory = C.c_void_p()
    iid = (C.c_ubyte * 16).from_buffer_copy(uuid.UUID('770aae78-f26f-4dba-a829-253c83d1b387').bytes_le)
    create = C.WinDLL('dxgi').CreateDXGIFactory1
    create.argtypes = [C.c_void_p, C.POINTER(C.c_void_p)]
    create.restype = W.LONG
    if create(C.byref(iid), C.byref(factory)) < 0:
        raise OSError('DXGI adapter enumeration failed')
    adapters = []
    try:
        for index in range(32):
            adapter = C.c_void_p()
            if _method(factory, 12, W.LONG, W.UINT, C.POINTER(C.c_void_p))(factory, index, C.byref(adapter)) < 0:
                break
            try:
                desc = _Desc()
                if _method(adapter, 10, W.LONG, C.POINTER(_Desc))(adapter, C.byref(desc)) >= 0 and not desc.flags & 2:
                    adapters.append(desc)
            finally:
                _method(adapter, 2, W.ULONG)(adapter)
    finally:
        _method(factory, 2, W.ULONG)(factory)
    if not adapters:
        raise OSError('No hardware GPU found')
    # NVIDIA device 0 is the default translation/OCR device. Otherwise use the
    # first hardware adapter rather than Microsoft's software renderer.
    desc = next((d for d in adapters if d.vendor == 0x10de), adapters[0])
    luid = f'luid_0x{desc.luid.high & 0xffffffff:08x}_0x{desc.luid.low:08x}'
    return desc.name, luid, desc.dedicated


class WindowsGPUUsage:
    def __init__(self):
        if sys.platform != 'win32':
            raise OSError('Windows GPU counters require Windows')
        self.name, self.luid, self.capacity = _adapter()
        self.pdh = C.WinDLL('pdh')
        self.query = C.c_void_p()
        self.pdh.PdhOpenQueryW.argtypes = [W.LPCWSTR, C.c_size_t, C.POINTER(C.c_void_p)]
        self.pdh.PdhAddEnglishCounterW.argtypes = [C.c_void_p, W.LPCWSTR, C.c_size_t, C.POINTER(C.c_void_p)]
        self.pdh.PdhCollectQueryData.argtypes = [C.c_void_p]
        self.pdh.PdhCloseQuery.argtypes = [C.c_void_p]
        self.pdh.PdhGetFormattedCounterArrayW.argtypes = [C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.POINTER(W.DWORD), C.c_void_p]
        if self.pdh.PdhOpenQueryW(None, 0, C.byref(self.query)) != 0:
            raise OSError('GPU performance query could not be opened')
        try:
            self.engine = self._add(r'\GPU Engine(*)\Utilization Percentage')
            self.memory = self._add(r'\GPU Adapter Memory(*)\Dedicated Usage')
            self.pdh.PdhCollectQueryData(self.query)  # utilization requires two samples
        except Exception:
            self.close()
            raise

    def _add(self, path):
        counter = C.c_void_p()
        if self.pdh.PdhAddEnglishCounterW(self.query, path, 0, C.byref(counter)) != 0:
            raise OSError('GPU performance counters unavailable')
        return counter

    def _values(self, counter):
        size, count = W.DWORD(), W.DWORD()
        self.pdh.PdhGetFormattedCounterArrayW(counter, 0x200, C.byref(size), C.byref(count), None)
        if not size.value:
            return []
        buffer = C.create_string_buffer(size.value)
        if self.pdh.PdhGetFormattedCounterArrayW(counter, 0x200, C.byref(size), C.byref(count), buffer) != 0:
            return []
        items = C.cast(buffer, C.POINTER(_Item))
        return [(items[i].name, items[i].value.double) for i in range(count.value)
                if items[i].value.status in (0, 1)]

    def sample(self):
        if self.pdh.PdhCollectQueryData(self.query) != 0:
            return {'gpu': None, 'vram': None}
        return aggregate_usage(self._values(self.engine), self._values(self.memory), self.luid, self.capacity)

    def close(self):
        if self.query:
            self.pdh.PdhCloseQuery(self.query)
            self.query = C.c_void_p()
