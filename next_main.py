"""Packaged launcher with readable startup diagnostics."""
import os,sys,traceback
from pathlib import Path
try:
    from app.next_main import main
    if __name__=='__main__':raise SystemExit(main())
except Exception:
    target=Path(os.environ.get('MERGEN_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'mergen-next')))
    target.mkdir(parents=True,exist_ok=True)
    (target/'startup-error.log').write_text(traceback.format_exc(),encoding='utf-8')
    raise
