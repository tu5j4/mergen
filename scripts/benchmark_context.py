"""Real CPU NLLB vs Qwen 0.6B proposals; references never enter model inputs."""
import argparse
import csv
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.context_model import QwenContextModel


class MemorySampler:
    def __init__(self):
        self.peak = 0
        self.inference_peak = 0
        self.measuring_inference = False
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    @staticmethod
    def current_mb():
        import psutil
        parent = psutil.Process()
        total = 0
        for process in [parent] + parent.children(recursive=True):
            try:
                total += process.memory_info().rss
            except psutil.Error:
                pass
        return total / 1024**2

    def run(self):
        import psutil
        parent = psutil.Process()
        while not self.done.is_set():
            total = 0
            for process in [parent] + parent.children(recursive=True):
                try:
                    total += process.memory_info().rss
                except psutil.Error:
                    pass
            self.peak = max(self.peak, total)
            if self.measuring_inference:
                self.inference_peak = max(self.inference_peak, total)
            self.done.wait(.2)


def publish(output, report):
    (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'results.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['id', 'episode', 'source', 'nllb', 'without_history', 'with_history',
                  'reference', 'base_ms', 'history_preparation_ms', 'without_ms', 'with_ms', 'without_status', 'with_status', 'error']
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in report['rows']:
            writer.writerow({k: "'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for k,v in row.items()})
    rows = []
    def esc(value):
        return html.escape(str(value))
    for row in report['rows']:
        history = '<br>'.join(esc(item['source']) for item in row['history'])
        rows.append('<tr>' + ''.join('<td>' + cell + '</td>' for cell in [
            esc(str(row['episode']) + ' / ' + str(row['id'])), history,
            esc(row['source']), esc(row['nllb']), esc(row['without_history']),
            esc(row['with_history']), esc(row['reference']),
            esc(f"{row['base_ms']:.0f} / {row['without_ms']:.0f} / {row['with_ms']:.0f} ms"),
            esc(row['with_status'] + ' ' + row['error'])]) + '</tr>')
    content = '''<!doctype html><html lang="tr"><meta charset="utf-8">
<title>mergen bağlam deneyi</title><style>
body{font:14px 'Segoe UI',sans-serif;margin:28px;background:#f7f8fa;color:#172033;text-transform:lowercase}
table{border-collapse:collapse;background:white;width:100%}td,th{border:1px solid #dde2e8;padding:12px;text-align:left;vertical-align:top;min-width:100px}th{background:#edf4ff}h1{font-size:26px}.note{max-width:1100px;line-height:1.7}
</style><h1>mergen · qwen 0.6b bağlam deneyi</h1>
<p class="note">bunlar deneysel önerilerdir; otomatik kalite puanı veya onay değildir.
referans çeviriler yalnızca bu tabloda gösterilir, modele verilmez.
geçmişteki türkçe metinler nllb taslaklarıdır. hem geçmişli hem geçmişsiz qwen sonucu gösterilir.
süreler ilk yükleme hariçtir. ocr ve ekran kartı bu testin kapsamında değildir.</p>'''
    content += '<p>' + esc(f"durum: {report['status']} · tamamlanan örnek: {len(report['rows'])} · ölçülen süreç ağacı tepe çalışma kümesi: {report.get('peak_working_set_mb',0):.0f} mb") + '</p>'
    if report.get('error'):
        content += '<p>hata: ' + esc(report['error']) + '</p>'
    content += '<p>nllb süresi yalnız mevcut repliği kapsar ve önbellek temizlenir. qwen süreleri buna eklenecek düzenleme maliyetidir. geçmiş hazırlama süresi ayrıca kaydedilir. çalışma kümesi toplamı paylaşılan belleği birden fazla sayabilir.</p>'
    if 'nllb_only_working_set_mb' in report:
        content += '<p>' + esc(f"qwen yüklenmeden önce nllb oturumu çalışma kümesi: {report['nllb_only_working_set_mb']:.0f} mb · bütün karşılaştırmanın tepe çalışma kümesi: {report['peak_working_set_mb']:.0f} mb") + '</p>'
    content += '<table><thead><tr>' + ''.join('<th>'+s+'</th>' for s in
        ['bölüm / kayıt', 'önceki kaynak replikler', 'kaynak', 'nllb', 'qwen geçmişsiz', 'qwen geçmişli', 'referans', 'süre nllb / geçmişsiz / geçmişli', 'teknik durum']) + '</tr></thead><tbody>'
    content += ''.join(rows) + '</tbody></table></html>'
    (output / 'rapor.html').write_text(content, encoding='utf-8')


def run(args):
    from app.storage import DATA_ROOT
    from app.core.translator import Translator
    from scripts.prepare_context_assets import prepare
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(status='hazırlanıyor', rows=[], peak_working_set_mb=0,
        started_at=datetime.now(timezone.utc).isoformat(), model='qwen3-0.6b-q8',
        cpu_only=True, context_size=2048, review_required=True)
    publish(output, report)
    sampler = MemorySampler()
    sampler.thread.start()
    context_model = translator = None
    try:
        print('qwen 0.6b dosyalari hazirlaniyor...', flush=True)
        assets = prepare(DATA_ROOT / 'context-test')
        report['assets'] = assets
        model_dir = DATA_ROOT / 'models/nllb-200-distilled-600M-ct2'
        if not (model_dir / 'model.bin').is_file():
            print('nllb 600m indiriliyor ve int8 olarak hazirlaniyor...', flush=True)
            from huggingface_hub import snapshot_download
            from ctranslate2.converters import TransformersConverter
            from transformers import AutoTokenizer
            snapshot = snapshot_download('facebook/nllb-200-distilled-600M',
                allow_patterns=['*.json', '*.model', '*.safetensors', 'pytorch_model.bin'])
            report['nllb_revision'] = Path(snapshot).name
            model_dir.parent.mkdir(parents=True, exist_ok=True)
            # A failed previous conversion remains visibly incomplete; overwrite
            # only this dedicated test model directory on retry.
            TransformersConverter(snapshot).convert(str(model_dir), quantization='int8', force=True)
            AutoTokenizer.from_pretrained(snapshot).save_pretrained(model_dir / 'tokenizer')
        started = time.perf_counter()
        translator = Translator(model_dir, device='cpu', beam_size=2)
        translator.translate(['Hello.'], 'eng_Latn')
        report['nllb_only_working_set_mb'] = MemorySampler.current_mb()
        context_model = QwenContextModel(assets['executable'], assets['model'], output, timeout=30)
        context_model.start()
        report['load_ms'] = (time.perf_counter()-started)*1000
        # Warm-up is explicit and excluded from per-example latency.
        warm = context_model.refine(['Hello.'], ['Merhaba.'])
        if warm.status != 'proposal':
            raise RuntimeError('qwen warmup failed: ' + warm.error)
        import psutil
        import importlib.metadata
        report['qwen_server_working_set_mb'] = psutil.Process(context_model.process.pid).memory_info().rss / 1024**2
        report['environment'] = dict(logical_cpus=os.cpu_count(), nllb_threads=max(1, (os.cpu_count() or 4)//2),
            qwen_threads=max(1, min(4, (os.cpu_count() or 2)//2)),
            packages={name: importlib.metadata.version(name) for name in
                      ('torch', 'transformers', 'ctranslate2', 'psutil')})
        sampler.measuring_inference = True
        report['status'] = 'çalışıyor'
        publish(output, report)
        fixture = json.loads(args.fixture.read_text(encoding='utf-8'))
        for case in fixture['cases']:
            print(f"ornek {len(report['rows'])+1}/{len(fixture['cases'])}", flush=True)
            previous = case['previous_sources'][-3:]
            translator.clear_cache()
            history_started = time.perf_counter()
            previous_translations = translator.translate(previous, 'eng_Latn', beam_size=2)
            history_ms = (time.perf_counter()-history_started)*1000
            translator.clear_cache()
            started = time.perf_counter()
            base = translator.translate([case['source']], 'eng_Latn', beam_size=2)
            baseline_ms = (time.perf_counter()-started)*1000
            history = [dict(source=s, translation=t) for s,t in zip(previous, previous_translations)]
            without = context_model.refine([case['source']], [base[-1]])
            with_history = context_model.refine([case['source']], [base[-1]], history)
            row = dict(id=case['id'], episode=case['episode'], source=case['source'],
                history=history, nllb=base[-1], without_history=without.translations[0],
                with_history=with_history.translations[0], reference=case['reference'],
                base_ms=baseline_ms, history_preparation_ms=history_ms,
                without_ms=without.elapsed_ms, with_ms=with_history.elapsed_ms,
                without_status=without.status, with_status=with_history.status,
                error='; '.join(s for s in (without.error, with_history.error) if s))
            report['rows'].append(row)
            report['peak_working_set_mb'] = sampler.peak/1024**2
            publish(output, report)
        report['status'] = 'tamamlandı'
        return 0
    except Exception as exc:
        report['status'] = 'başarısız'
        report['error'] = str(exc)
        raise
    finally:
        if context_model:
            context_model.close()
        if translator:
            translator.close()
        sampler.done.set()
        sampler.thread.join(timeout=2)
        report['peak_working_set_mb'] = sampler.peak/1024**2
        report['inference_peak_working_set_mb'] = sampler.inference_peak/1024**2
        publish(output, report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('fixture', type=Path)
    parser.add_argument('output', type=Path)
    raise SystemExit(run(parser.parse_args()))
