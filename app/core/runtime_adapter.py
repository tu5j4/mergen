"""Report the actual inference device, preserving vendor-specific CUDA runtimes."""


def _identity(metadata):
    out = {}
    if not isinstance(metadata, dict):
        return out
    name = metadata.get('name')
    identity = metadata.get('uuid')
    if isinstance(name, str) and name:
        out['name'] = name
    if isinstance(identity, str) and identity:
        out['uuid'] = identity
    return out


def adapter_selection(device, backend='local', metadata=None):
    """Resolve one selection, preferring the identity the runtime really loaded.

    ``metadata`` is the dict reported by RuntimeClient/scripts.runtime_worker.py.
    An actual CPU fallback always wins; a nominally configured ``cuda`` device
    must never be presented as a GPU when the worker initialized on CPU.
    """
    device = str(device or '').lower()
    meta = metadata if isinstance(metadata, dict) else {}
    meta_backend = str(meta.get('backend') or '').lower()
    if device.startswith('cpu') or meta_backend == 'cpu':
        return dict(backend='cpu', device_index=0)
    if meta_backend in ('nvidia', 'amd', 'intel'):
        try:
            index = int(meta.get('device_index', 0))
        except (TypeError, ValueError):
            index = 0
        return dict(backend=meta_backend, device_index=max(0, index), **_identity(meta))
    if device.startswith('xpu'):
        vendor = 'intel'
    elif device.startswith(('cuda', 'gpu')):
        vendor = backend if backend in ('nvidia', 'amd') else ('nvidia' if backend == 'local' else 'unknown')
    else:
        vendor = 'unknown'
    try:
        index = int(device.split(':', 1)[1]) if ':' in device else 0
    except ValueError:
        return dict(backend='unknown', device_index=0)
    return dict(backend=vendor, device_index=max(0, index))


def ocr_adapter(engine, paddle_backend='local', manga_backend='local'):
    selections = []
    paddle = getattr(engine, 'paddle', None)
    if paddle is not None:
        selections.append(adapter_selection(getattr(engine, 'paddle_device', None),
                                            paddle_backend, getattr(paddle, 'adapter', None)))
    manga = getattr(engine, 'manga', None)
    if manga is not None:
        selections.append(adapter_selection(getattr(manga, 'device', None),
                                            manga_backend, getattr(manga, 'adapter', None)))
    gpu = [s for s in selections if s['backend'] != 'cpu']
    if not gpu:
        return dict(backend='cpu' if selections else 'unknown', device_index=0)
    # Two OCR runtimes on different physical GPUs cannot be represented as one
    # adapter; report unknown instead of guessing by backend alone.
    return gpu[0] if all(s == gpu[0] for s in gpu) else dict(backend='unknown', device_index=0)
