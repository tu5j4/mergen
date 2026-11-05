"""Optional local Rust geometry kernels. No model or text crosses this interface."""
import ctypes as c
import math
import os
import sys
from pathlib import Path


class BoxData(c.Structure):
    _fields_=[('x1',c.c_double),('y1',c.c_double),('x2',c.c_double),('y2',c.c_double),('bubble',c.c_int32),('panel',c.c_int32)]


class Rect(c.Structure):
    _fields_=[('x',c.c_double),('y',c.c_double),('w',c.c_double),('h',c.c_double)]


_lib=None
_error=''
stats=dict(group_calls=0,overlap_calls=0,fallbacks=0)
if sys.platform == 'win32' and os.environ.get('MERGEN_RUST_ENABLED', '0') != '0':
    try:
        _lib=c.CDLL(str(Path(__file__).with_name('mergen_rust.dll')))
        _lib.mergen_geometry_abi.restype=c.c_uint32
        _lib.mergen_geometry_sizes.restype=c.c_uint64
        if _lib.mergen_geometry_abi()!=1 or _lib.mergen_geometry_sizes()!=((c.sizeof(BoxData)<<32)|c.sizeof(Rect)):
            raise RuntimeError('rust arayüzü eşleşmiyor')
        _lib.mergen_group_boxes.argtypes=[c.POINTER(BoxData),c.c_size_t,c.c_double,c.c_double,c.c_uint32,c.POINTER(c.c_uint32)]
        _lib.mergen_group_boxes.restype=c.c_int32
        _lib.mergen_overlap_indices.argtypes=[c.POINTER(Rect),c.POINTER(Rect),c.c_size_t,c.POINTER(c.c_uint32),c.c_size_t]
        _lib.mergen_overlap_indices.restype=c.c_int32
    except (OSError,RuntimeError,AttributeError) as exc:
        _error=str(exc);_lib=None


def require_native():
    if _lib is None:raise RuntimeError('rust modülü yüklenemedi: '+_error)
    return dict(loaded=True,abi=1,engine='rust geometry',**stats)


def _numbers(values):
    values=tuple(float(v) for v in values)
    if not all(math.isfinite(v) and abs(v)<=1e12 for v in values):raise ValueError('unsupported coordinates')
    return values


def _ids(values,n):
    if values is None:return [-1]*n
    if len(values)!=n:raise ValueError('invalid identifiers')
    mapped={}
    return [-1 if value is None else mapped.setdefault(value,len(mapped)) for value in values]


def group(boxes,gap_ratio,bubble_ids,panel_ids,same_bubble_gap_ratio,allow_short_bubble_columns):
    if _lib is None:return None
    n=len(boxes)
    if n>8192:return None
    try:
        gap,ratio=_numbers((gap_ratio,0 if same_bubble_gap_ratio is None else same_bubble_gap_ratio))
        bubbles,panels=_ids(bubble_ids,n),_ids(panel_ids,n)
        data=(BoxData*n)(*(BoxData(*_numbers((b.x1,b.y1,b.x2,b.y2)),bubbles[i],panels[i]) for i,b in enumerate(boxes)))
    except (ValueError,TypeError,OverflowError):stats['fallbacks']+=1;return None
    flags=int(bubble_ids is not None)|int(panel_ids is not None)*2|int(same_bubble_gap_ratio is not None)*4|int(allow_short_bubble_columns)*8
    roots=(c.c_uint32*n)()
    code=_lib.mergen_group_boxes(data,n,gap,ratio,flags,roots)
    if code!=0:raise RuntimeError('rust kutu hesabı başarısız')
    stats['group_calls']+=1
    groups={}
    for i,root in enumerate(roots):groups.setdefault(root,[]).append(i)
    return list(groups.values())


class RectIndex:
    """Geometry-only mirror; caller records every append/replace to its owned list."""
    def __init__(self,blocks):
        self.owner=blocks;self.n=0;self.capacity=max(32,len(blocks)+32);self.valid=True
        self.data=(Rect*self.capacity)();self.output=(c.c_uint32*self.capacity)()
        for block in blocks:self.append(block)

    def matches(self,blocks):return self.owner is blocks and self.n==len(blocks)

    def _rect(self,item):return Rect(*_numbers((item['x'],item['y'],item['w'],item['h'])))

    def append(self,item):
        if self.n==self.capacity:
            self.capacity*=2;larger=(Rect*self.capacity)()
            c.memmove(larger,self.data,c.sizeof(self.data));self.data=larger
            self.output=(c.c_uint32*self.capacity)()
        try:self.data[self.n]=self._rect(item)
        except (ValueError,TypeError,OverflowError):self.valid=False
        self.n+=1

    def replace(self,index,item):
        try:self.data[index]=self._rect(item)
        except (ValueError,TypeError,OverflowError):self.valid=False

    def query(self,item):
        if not self.valid or self.n>8192:return None
        try:query=self._rect(item)
        except (ValueError,TypeError,OverflowError):stats['fallbacks']+=1;return None
        count=_lib.mergen_overlap_indices(c.byref(query),self.data,self.n,self.output,self.capacity)
        if count<0 or count>self.n:raise RuntimeError('rust örtüşme hesabı başarısız')
        stats['overlap_calls']+=1
        return list(self.output[:count])

    def retain_tail(self,blocks):
        keep=len(blocks);drop=self.n-keep
        if drop<0:raise RuntimeError('rust kutu dizini eşleşmiyor')
        if keep:c.memmove(self.data,c.byref(self.data,drop*c.sizeof(Rect)),keep*c.sizeof(Rect))
        self.n=keep;self.owner=blocks


def rect_index(blocks,previous=None):
    if _lib is None:return None
    return previous if previous is not None and previous.matches(blocks) else RectIndex(blocks)
