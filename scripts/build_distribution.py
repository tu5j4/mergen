"""Create current developer and source-install packages without local data."""
import argparse
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.export_next_source import ROOT, export, source_files


def build(output, source=ROOT):
    output = Path(output).absolute()
    source = Path(source).resolve()
    if output.exists():
        raise FileExistsError('choose a new distribution directory')
    if source.is_relative_to(output.resolve()):
        raise ValueError('unsafe output directory')
    source_files(source)
    export(output / 'github', source)
    program = output / 'kolay-kurulum/program'
    for path in source_files(source):
        relative = path.relative_to(source)
        if relative.parts[0] in ('tests', 'docs', '.github'):
            continue
        target = program / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for name in ('kurulum', 'baslat'):
        (output / 'kolay-kurulum' / (name + '.bat')).write_bytes(
            ('@echo off\r\ncall "%~dp0program\\' + name + '.bat" %*\r\n').encode('utf-8'))
    (output / 'kolay-kurulum/beni-oku.txt').write_text(
        'mergen\n\nilk kurulum: kurulum.bat\nacilis: baslat.bat\n'
        'modeller ve cihaz kutuphaneleri uygulamanin modeller sayfasindan kurulur.\n'
        'exe kurulumu icin github releases sayfasindaki guncel paketi kullanin.\n', encoding='utf-8')
    return output


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    build(parser.parse_args().output)
