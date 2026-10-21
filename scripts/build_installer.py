"""Compile the per-user installer with lowercase Turkish wizard messages."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def main():
    compiler = ROOT / 'build-tools/inno/ISCC.exe'
    language = compiler.parent / 'Languages/Turkish.isl'
    # Keep section names, keys and compiler directives intact.
    lines = []
    for line in language.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith(';'):
            key, value = line.split('=', 1)
            line = key + '=' + value.replace('İ', 'i').lower()
        lines.append(line)
    (ROOT / 'build-tools/turkish-lowercase.isl').write_text('\n'.join(lines)+'\n', encoding='utf-8-sig')
    subprocess.run([str(compiler), str(ROOT / 'installer/mergen-next.iss')], check=True)


if __name__ == '__main__':
    main()
