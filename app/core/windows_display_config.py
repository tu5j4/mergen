"""Bridge friendly Qt monitor names to source GDI device names using active paths."""
def windows_display_names():
    import ctypes as c
    from ctypes import wintypes as w
    user=c.WinDLL('user32',use_last_error=True)
    class Luid(c.Structure):_fields_=[('low',c.c_uint32),('high',c.c_int32)]
    class Header(c.Structure):_fields_=[('type',c.c_uint32),('size',c.c_uint32),('adapter',Luid),('id',c.c_uint32)]
    class Source(c.Structure):_fields_=[('adapter',Luid),('id',c.c_uint32),('mode',c.c_uint32),('status',c.c_uint32)]
    class Target(c.Structure):
        _fields_=[('adapter',Luid),('id',c.c_uint32),('mode',c.c_uint32),('technology',c.c_uint32),('rotation',c.c_uint32),('scaling',c.c_uint32),('refresh_num',c.c_uint32),('refresh_den',c.c_uint32),('scanline',c.c_uint32),('available',w.BOOL),('status',c.c_uint32)]
    class Path(c.Structure):_fields_=[('source',Source),('target',Target),('flags',c.c_uint32)]
    class Mode(c.Structure):_fields_=[('type',c.c_uint32),('id',c.c_uint32),('adapter',Luid),('payload',c.c_uint64*6)]
    class SourceName(c.Structure):_fields_=[('header',Header),('name',w.WCHAR*32)]
    class TargetName(c.Structure):
        _fields_=[('header',Header),('flags',c.c_uint32),('technology',c.c_uint32),('manufacturer',c.c_uint16),('product',c.c_uint16),('connector',c.c_uint32),('friendly',w.WCHAR*64),('device_path',w.WCHAR*128)]
    user.GetDisplayConfigBufferSizes.argtypes=[c.c_uint32,c.POINTER(c.c_uint32),c.POINTER(c.c_uint32)]
    user.GetDisplayConfigBufferSizes.restype=c.c_long
    user.QueryDisplayConfig.argtypes=[c.c_uint32,c.POINTER(c.c_uint32),c.POINTER(Path),c.POINTER(c.c_uint32),c.POINTER(Mode),c.c_void_p]
    user.QueryDisplayConfig.restype=c.c_long
    user.DisplayConfigGetDeviceInfo.argtypes=[c.c_void_p];user.DisplayConfigGetDeviceInfo.restype=c.c_long
    for _ in range(3):
        paths_count=c.c_uint32();modes_count=c.c_uint32()
        error=user.GetDisplayConfigBufferSizes(2,c.byref(paths_count),c.byref(modes_count))
        if error:raise c.WinError(error)
        paths=(Path*paths_count.value)();modes=(Mode*modes_count.value)()
        error=user.QueryDisplayConfig(2,c.byref(paths_count),paths,c.byref(modes_count),modes,None)
        if error==122:continue
        if error:raise c.WinError(error)
        aliases={}
        for path in paths[:paths_count.value]:
            source=SourceName();source.header=Header(1,c.sizeof(SourceName),path.source.adapter,path.source.id)
            target=TargetName();target.header=Header(2,c.sizeof(TargetName),path.target.adapter,path.target.id)
            if user.DisplayConfigGetDeviceInfo(c.byref(source)) or user.DisplayConfigGetDeviceInfo(c.byref(target)):continue
            friendly=target.friendly.strip().casefold();gdi=source.name.casefold()
            if not friendly:continue
            if friendly in aliases and aliases[friendly]!=gdi:aliases[friendly]=None
            else:aliases[friendly]=gdi
        return aliases
    raise RuntimeError('ekran düzeni okunurken değişti; yeniden deneyin')
