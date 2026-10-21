"""Create a read-only source snapshot, held-out fixture and launchable WSB."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.export_next_source import export


def prepare(database, output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('choose a new test directory')
    # Read-only SQLite URI: this preparation must not change approval state.
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    cases = []
    try:
        for episode in (11, 12):
            rows = list(connection.execute('SELECT * FROM candidates WHERE episode=? ORDER BY en_start', (episode,)))
            eligible = [i for i, row in enumerate(rows) if i >= 3 and 3 <= len(row['english'].split()) <= 22]
            if len(eligible) < 6:
                raise ValueError('not enough evaluation examples')
            for index in range(6):
                i = eligible[(index*len(eligible))//6]
                row = rows[i]
                previous = [p['english'] for p in rows[max(0, i-3):i]
                            if 0 <= row['en_start']-p['en_end'] <= 30]
                cases.append(dict(id=row['id'], episode=episode, source=row['english'],
                    previous_sources=previous, reference=row['turkish']))
    finally:
        connection.close()
    input_root = output / 'input'
    results = output / 'results'
    input_root.mkdir(parents=True)
    results.mkdir()
    export(input_root / 'source')
    (input_root / 'cases.json').write_text(json.dumps(dict(cases=cases,
        reference_policy='reference is display-only, never passed to either model'),
        ensure_ascii=False, indent=2), encoding='utf-8')
    config = ET.Element('Configuration')
    for name, value in [('MemoryInMB','8192'),('Networking','Enable'),('VGpu','Disable'),
                        ('AudioInput','Disable'),('VideoInput','Disable'),('ClipboardRedirection','Disable')]:
        ET.SubElement(config, name).text = value
    mapped = ET.SubElement(config, 'MappedFolders')
    for host, guest, readonly in [(input_root, 'C:\\mergen-input', 'true'), (results, 'C:\\mergen-results', 'false')]:
        folder = ET.SubElement(mapped, 'MappedFolder')
        ET.SubElement(folder, 'HostFolder').text = str(host)
        ET.SubElement(folder, 'SandboxFolder').text = guest
        ET.SubElement(folder, 'ReadOnly').text = readonly
    logon = ET.SubElement(config, 'LogonCommand')
    ET.SubElement(logon, 'Command').text = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        'C:\\mergen-input\\source\\scripts\\sandbox_context.ps1')
    ET.indent(config)
    ET.ElementTree(config).write(output / 'baslat.wsb', encoding='utf-8', xml_declaration=True)
    print(output / 'baslat.wsb')
    return output / 'baslat.wsb'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('database', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    prepare(args.database, args.output)
