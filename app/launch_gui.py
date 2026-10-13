"""Start the Qt window without a lingering console, reporting startup failures."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run() -> int:
    try:
        from main import main
        return main()
    except Exception as exc:
        details = traceback.format_exc()
        log = ROOT / 'logs' / 'baslatma-hatasi.log'
        try:
            log.parent.mkdir(exist_ok=True)
            log.write_text(details, encoding='utf-8')
            hint = f'\n\nAyrıntılar: {log}'
        except OSError:
            hint = ''
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, f'mergen başlatılamadı.\n{type(exc).__name__}: {exc}{hint}',
                'mergen', 0x10)
        else:
            print(details, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(run())
