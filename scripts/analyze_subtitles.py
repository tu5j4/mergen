"""Build a local, unapproved subtitle-pair review set without model inference.

Timing confidence is not semantic translation quality. Original files are read
only. No extracted pair is added to the application's translation glossary.
"""
import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str
    line: int
    style: str = ''


def timestamp(value):
    hours, minutes, seconds = value.strip().replace(',', '.').split(':')
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_text(value):
    value = re.sub(r'\{[^}]*\}', '', value)
    value = re.sub(r'<[^>]*>', '', value)
    value = value.replace(r'\N', ' ').replace(r'\n', ' ').replace(r'\h', ' ')
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()


def read_ass(path):
    fields = None
    events = False
    cues = []
    excluded = Counter()
    styles = Counter()
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if line.startswith('['):
            events = line.strip().lower() == '[events]'
        if not events:
            continue
        if line.startswith('Format:'):
            fields = [s.strip().lower() for s in line.split(':', 1)[1].split(',')]
        if not line.startswith('Dialogue:') or not fields:
            continue
        parts = line.split(':', 1)[1].lstrip().split(',', len(fields) - 1)
        if len(parts) != len(fields):
            excluded['malformed'] += 1
            continue
        row = dict(zip(fields, parts))
        style = row.get('style', '')
        styles[style] += 1
        # Explicit dialogue families observed in these files; unknown styles
        # are retained in inventory rather than silently treated as dialogue.
        if not re.fullmatch(r'(default(?:italics)?(?:top)?|alt|flashback(?:italics)?)', style, re.I):
            excluded['non_dialogue_style'] += 1
            continue
        if re.search(r'\\p[1-9]\d*\b', row['text']):
            excluded['drawing'] += 1
            continue
        text = clean_text(row['text'])
        start, end = timestamp(row['start']), timestamp(row['end'])
        if not text or end <= start:
            excluded['empty_or_invalid'] += 1
            continue
        cues.append(Cue(start, end, text, number, style))
    # Multiple display layers sometimes repeat identical dialogue.
    unique = {(round(c.start, 3), round(c.end, 3), c.text): c for c in cues}
    excluded['duplicate'] += len(cues) - len(unique)
    return sorted(unique.values(), key=lambda c: (c.start, c.end)), dict(excluded), dict(styles)


def read_srt(path):
    text = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    cues = []
    malformed = 0
    for number, block in enumerate(re.split(r'\n\s*\n', text.strip()), 1):
        lines = block.splitlines()
        time_index = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if time_index is None:
            malformed += 1
            continue
        times = re.match(r'\s*(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)', lines[time_index])
        if not times:
            malformed += 1
            continue
        start, end = map(timestamp, times.groups())
        value = clean_text(' '.join(lines[time_index + 1:]))
        if value and end > start:
            cues.append(Cue(start, end, value, number))
    return sorted(cues, key=lambda c: (c.start, c.end)), malformed


def align(english, turkish, tolerance=.4):
    candidates = defaultdict(list)
    reverse = defaultdict(list)
    for i, en in enumerate(english):
        for j, tr in enumerate(turkish):
            if tr.start > en.start + tolerance:
                break
            if abs(en.start - tr.start) > tolerance or abs(en.end - tr.end) > tolerance:
                continue
            intersection = max(0, min(en.end, tr.end) - max(en.start, tr.start))
            union = max(en.end, tr.end) - min(en.start, tr.start)
            iou = intersection / union if union else 0
            if iou < .7:
                continue
            score = iou - .1 * (abs(en.start - tr.start) + abs(en.end - tr.end))
            candidates[i].append((score, j, iou))
            reverse[j].append((score, i, iou))
    for rows in list(candidates.values()) + list(reverse.values()):
        rows.sort(reverse=True)
    pairs = []
    for i, rows in candidates.items():
        score, j, iou = rows[0]
        if reverse[j][0][1] != i:
            continue
        if (len(rows) > 1 and score - rows[1][0] < .1) or (len(reverse[j]) > 1 and score - reverse[j][1][0] < .1):
            continue
        pairs.append((i, j, round(iou, 4)))
    return sorted(pairs)


def episode(path):
    pattern = r'S\d+E(\d+)' if path.suffix.lower() == '.srt' else r'_-_(\d+)\.ass$'
    match = re.search(pattern, path.name, re.I)
    return int(match[1]) if match else None


def analyze(source, output):
    source, output = Path(source).resolve(), Path(output).absolute()
    if not source.is_dir():
        raise ValueError('subtitle directory missing')
    if output.exists() or output.resolve() == source or source.is_relative_to(output.resolve()) or output.resolve().is_relative_to(source):
        raise ValueError('choose a new output directory outside original subtitles')
    files = defaultdict(dict)
    for path in source.iterdir():
        if path.suffix.lower() not in ('.srt', '.ass'):
            continue
        number = episode(path)
        if number is None:
            raise ValueError('episode not recognized: ' + path.name)
        language = 'en' if path.suffix.lower() == '.srt' else 'tr'
        if language in files[number]:
            raise ValueError('multiple files for episode/language: ' + str(number))
        files[number][language] = path
    output.mkdir(parents=True)
    db = sqlite3.connect(output / 'inceleme.sqlite3')
    db.executescript('''
        CREATE TABLE sources (episode INTEGER, language TEXT, filename TEXT, sha256 TEXT,
                              PRIMARY KEY(episode, language));
        CREATE TABLE candidates (id INTEGER PRIMARY KEY, episode INTEGER, split TEXT,
            en_start REAL, en_end REAL, tr_start REAL, tr_end REAL,
            en_cue INTEGER, tr_line INTEGER, tr_style TEXT, english TEXT, turkish TEXT,
            timing_iou REAL, status TEXT DEFAULT 'inceleme_bekliyor',
            approved INTEGER DEFAULT 0 CHECK (approved IN (0,1)));
    ''')
    summary = []
    try:
        for number, languages in sorted(files.items()):
            if set(languages) != {'en', 'tr'}:
                summary.append(dict(episode=number, missing=sorted({'en', 'tr'} - languages.keys())))
                continue
            for language, path in languages.items():
                db.execute('INSERT INTO sources VALUES (?,?,?,?)',
                    (number, language, path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
            en, malformed = read_srt(languages['en'])
            tr, excluded, styles = read_ass(languages['tr'])
            pairs = align(en, tr)
            for i, j, iou in pairs:
                a, b = en[i], tr[j]
                db.execute('''INSERT INTO candidates
                    (episode,split,en_start,en_end,tr_start,tr_end,en_cue,tr_line,tr_style,english,turkish,timing_iou)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (number, 'degerlendirme' if number >= 11 else 'gelistirme',
                     a.start, a.end, b.start, b.end, a.line, b.line, b.style, a.text, b.text, iou))
            summary.append(dict(episode=number, english_cues=len(en), turkish_dialogue=len(tr),
                timing_candidates=len(pairs), unmatched_english=len(en)-len(pairs),
                unmatched_turkish=len(tr)-len(pairs), excluded_turkish=excluded,
                turkish_styles=styles, malformed_srt=malformed))
        db.commit()
        cursor = db.execute('SELECT * FROM candidates ORDER BY episode,en_start')
        with (output / 'eslesmeler.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow([c[0] for c in cursor.description])
            for row in cursor:
                writer.writerow(["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for v in row])
        repeated = defaultdict(Counter)
        for en, tr in db.execute("SELECT english,turkish FROM candidates WHERE split='gelistirme'"):
            repeated[en.casefold()][tr] += 1
        repeated = [dict(english=en, occurrences=sum(targets.values()), turkish_variants=dict(targets))
                    for en, targets in repeated.items() if sum(targets.values()) >= 2]
        repeated.sort(key=lambda r: -r['occurrences'])
        report = dict(episodes=summary, candidates=db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],
            approved=0, matched_on='mutual unique timing; start/end within 0.4s; interval iou >= 0.7',
            warning='timing similarity is not semantic validation; split/merged dialogue remains unmatched',
            evaluation_episodes=[11, 12], repeated_development_phrases=repeated)
        (output / 'rapor.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# bocchi altyazı incelemesi', '',
            '12 bölümlük yerel inceleme seti. orijinal dosyalar değiştirilmedi.', '',
            '| bölüm | ingilizce satır | türkçe konuşma | zaman eşleşmesi adayı |',
            '|---|---:|---:|---:|']
        for row in summary:
            if 'missing' in row:
                lines.append(f"| {row['episode']:02} | eksik | eksik | 0 |")
            else:
                lines.append(f"| {row['episode']:02} | {row['english_cues']} | {row['turkish_dialogue']} | {row['timing_candidates']} |")
        lines += ['', f"toplam {report['candidates']} aday; onaylanmış kayıt: 0.", '',
            'şarkı, tabela ve çizim stilleri ayıklandı. tek satır / iki satır farkları zorla eşleştirilmedi.',
            'zaman eşleşmesi anlam doğruluğu garantisi değildir; bütün adaylar inceleme bekliyor.',
            '11 ve 12. bölümler değerlendirme için ayrıldı; sözlük çıkarımına katılmamalıdır.', '',
            '`eslesmeler.csv`: excel ile açılabilir inceleme tablosu.',
            '`inceleme.sqlite3`: kaynak dosya özetleri ve onaysız aday veritabanı.',
            '`rapor.json`: stil sayıları, eşleşmeyen satırlar ve tekrarlanan ifadeler.', '',
            'veriler uygulama sözlüğüne eklenmedi; model eğitilmedi. font kurulumu yapılmadı.']
        (output / 'oku.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return report
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = analyze(args.source, args.output)
    print(json.dumps({'episodes': len(report['episodes']), 'candidates': report['candidates'], 'approved': 0}))
