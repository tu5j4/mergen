"""
Hızlı işlem hattı — iki iş parçacığı:

1) TAKİPÇİ (bu QThread, ~15 fps):
   ekranı yakalar, kaydırma miktarını tahmin eder, mevcut çevirileri içerikle
   birlikte kaydırır. Sayfa tamamen değişirse temizler.

2) OCR İŞÇİSİ (ThreadPoolExecutor, 1 thread):
   kaydırma durunca SADECE henüz okunmamış yeni şeridi OCR'lar ve çevirir;
   sonuçları parça parça (yukarıdan aşağı) takipçiye gönderir.

Çeviriler "içerik koordinatında" (sayfa üzerinde) tutulur; böylece webtoon'da
yukarı/aşağı kaydırınca tekrar OCR yapılmadan anında görünür.
"""
from __future__ import annotations

import queue
import re
from difflib import SequenceMatcher
import json
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from ..config import LANGS, PROJECT_ROOT, Settings
from .capture import ScreenCapturer, estimate_vshift, frame_diff, thumbnail_gray, to_gray
from .session_context import SessionContext

EDGE_PX = 3          # kenara bu kadar yakın balonlar "yarım" sayılır
STRIP_MARGIN = 48    # yeni şerit okunurken önceki alana taşma payı (px)
MAX_BLOCKS = 3000
_CONTEXT_UNSET = object()


def _merge_intervals(iv: list[list[int]]) -> list[list[int]]:
    out: list[list[int]] = []
    for a, b in sorted([list(i) for i in iv if i[1] > i[0]]):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _subtract(span: tuple[int, int], ivs: list[list[int]]) -> list[tuple[int, int]]:
    a, b = span
    res, cur = [], a
    for x, y in ivs:
        if y <= cur:
            continue
        if x >= b:
            break
        if x > cur:
            res.append((cur, min(x, b)))
        cur = max(cur, y)
        if cur >= b:
            break
    if cur < b:
        res.append((cur, b))
    return res


def _overlap_ratio(a: dict, b: dict) -> float:
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    return (ix * iy) / max(1.0, min(a["w"] * a["h"], b["w"] * b["h"]))


def _more_complete(new: dict, old: dict) -> bool:
    """Only replace the same English passage when a reread preserves its words.

    Length alone is not quality: require matching language/panel, spatial
    containment and almost all old words in order, plus at least two new words.
    """
    if new.get('source_lang') != 'en' or old.get('source_lang') != 'en':
        return False
    if new.get('panel') != old.get('panel'):
        return False
    old_area, new_area = old['w'] * old['h'], new['w'] * new['h']
    ix = max(0, min(new['x'] + new['w'], old['x'] + old['w']) - max(new['x'], old['x']))
    iy = max(0, min(new['y'] + new['h'], old['y'] + old['h']) - max(new['y'], old['y']))
    if ix * iy < old_area * .85 or not old_area * .9 <= new_area <= old_area * 3:
        return False
    before = re.findall(r"[a-z0-9]+", old.get('src', '').lower())
    after = re.findall(r"[a-z0-9]+", new.get('src', '').lower())
    if len(before) < 2 or len(after) < len(before) + 2:
        return False
    matches = sum(b.size for b in SequenceMatcher(None, before, after, autojunk=False).get_matching_blocks())
    return matches >= len(before) * .9


class TranslationWorker(QObject):
    status = Signal(str)
    devices = Signal(str)
    error = Signal(str)
    blocks_ready = Signal(list)
    clear_requested = Signal()
    hide_request = Signal(bool)

    def __init__(self, settings: Settings, overlay_excluded: bool, overlay_handle=None) -> None:
        super().__init__()
        self.s = settings
        self._lock = threading.Lock()
        self._running = True
        self._active = False
        self._force = False
        self._region: tuple | None = None
        self._region_version = 0
        self._lang = settings.source_lang
        self._ocr_engine = settings.ocr_engine
        self._ocr_version = 0
        self._overlay_excluded = overlay_excluded
        self._overlay_handle = overlay_handle
        self._overlay_areas = []
        self._hide_ack = threading.Event()
        self._overlay_has_content = False
        self._session_context = SessionContext()
        self._context_enabled = settings.session_context
        self._context_version = 0

        self.ocr = None
        self.translator = None
        self._loaded_lang: str | None = None
        self._loaded_ocr_engine: str | None = None
        self._loaded_ocr_version = -1

        self._executor: ThreadPoolExecutor | None = None
        self._job: Future | None = None
        self._job_full_retry = False
        self._retry_full_viewport = False
        self._partials: queue.Queue = queue.Queue()
        self._partial_ready = threading.Event()
        self._gen = 0

        self._H, self._sx, self._sy = 1, 1.0, 1.0
        self._reset_state_vars()

    # ------------------ thread-safe API ------------------
    def set_region(self, cap_rect, logical_size) -> None:
        with self._lock:
            self._region = (*cap_rect, *logical_size)
            self._region_version += 1

    def set_active(self, active: bool) -> None:
        with self._lock:
            self._active = active

    def force_once(self) -> None:
        with self._lock:
            self._force = True

    def set_language(self, lang: str) -> None:
        with self._lock:
            self._lang = lang

    def set_ocr_engine(self, engine: str) -> None:
        with self._lock:
            self._ocr_engine = engine
            self._ocr_version += 1
            self.s.ocr_engine = engine

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._active = False
        self._gen += 1
        self._hide_ack.set()
        self._partial_ready.set()

    def ack_hidden(self) -> None:
        self._hide_ack.set()

    def set_overlay_areas(self,areas) -> None:
        with self._lock:self._overlay_areas=list(areas)

    def reset_translation_context(self, enabled: bool | None = None) -> None:
        with self._lock:
            if enabled is not None:
                self._context_enabled = enabled
                self.s.session_context = enabled
            self._context_version += 1

    def _clear_translation_context(self) -> None:
        self._session_context = SessionContext()
        if self.translator is not None:
            self.translator.clear_cache()

    # ------------------ durum ------------------
    def _reset_state_vars(self) -> None:
        self.scroll_y = 0
        self.content_blocks: list[dict] = []
        self.processed: list[list[int]] = []
        self._attempted_scroll: int | None = None
        self._job_failures = 0
        self._retry_after = 0.0
        self._job_full_retry = False
        self._retry_full_viewport = False

    def _write_scan_diagnostic(self, diagnostic: dict) -> None:
        # Only stage/count/geometry metadata: never store the captured image
        # or recognized/translated dialogue. A diagnostic failure is harmless.
        self._last_scan_diagnostic = diagnostic
        try:
            folder = PROJECT_ROOT / "logs"
            folder.mkdir(exist_ok=True)
            (folder / "son_tarama.json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _reset_content(self) -> None:
        self._gen += 1                      # çalışan iş varsa sonuçları geçersiz
        self._reset_state_vars()
        self._emit_clear()

    def _emit_clear(self) -> None:
        if self._overlay_has_content:
            self._overlay_has_content = False
            self.clear_requested.emit()

    def _emit_visible(self) -> None:
        H, sx, sy = self._H, self._sx, self._sy
        out = []
        for b in self.content_blocks:
            y = b["y"] - self.scroll_y
            if y + b["h"] < 0 or y > H:
                continue
            out.append({"x": b["x"] / sx, "y": y / sy, "w": b["w"] / sx, "h": b["h"] / sy,
                        "text": b["text"], "bg": b["bg"], "vertical": b["vertical"],
                        "source_lang": b.get("source_lang", self._lang)})
        if out:
            self._overlay_has_content = True
            self.blocks_ready.emit(out)
        else:
            self._emit_clear()

    # ------------------ model yükleme ------------------
    def _load_translator(self) -> None:
        from .translator import Translator
        self.status.emit("Çeviri modeli yükleniyor…")
        self.translator = Translator(self.s.model_path, self.s.beam_size, self.s.cache_size,
                                     device='cpu' if self.s.use_gpu == 'no' else 'auto', backend=self.s.translation_backend)

    def _load_ocr(self, lang: str) -> None:
        from .ocr import OCREngine
        self.status.emit(f"OCR yükleniyor: {LANGS[lang]['name']}…")
        if self.ocr is not None:
            self.ocr.close()
        self.ocr = None
        self.ocr = OCREngine(lang, self.s)
        self._loaded_lang = lang
        self._loaded_ocr_engine = self._ocr_engine
        self._loaded_ocr_version = self._ocr_version
        manga = (f" + manga-ocr ({self.ocr.manga.device.upper()}, izole)"
                 if self.ocr.manga is not None else "")
        if self.ocr.manga_warning:
            manga += ' [manga uyarısı]'
        if self.ocr.paddle is not None:
            paddle_device = self.ocr.paddle_device or "cpu"
            paddle_model = self.ocr.paddle_model_kind or "Bilinmeyen"
            manga += f" + PaddleOCR {paddle_model} ({paddle_device.upper()})"
            ocr_on_gpu = paddle_device.startswith(("gpu", "cuda", "xpu"))
        else:
            ocr_on_gpu = self.ocr.gpu
        self.devices.emit(
            f"OCR: {'GPU ✅' if ocr_on_gpu else 'CPU ⚠️'}{manga}   |   "
            f"Çeviri: {'GPU ✅' if self.translator.device.startswith(('cuda','xpu')) else 'CPU ⚠️'}"
        )
        self.status.emit(f"Hazır: {LANGS[lang]['name']}")
        # Isınma: ilk çağrıdaki gecikmeyi kullanıcı hissetmesin
        try:
            dummy = np.full((64, 256, 3), 255, np.uint8)
            self.ocr.process(dummy)
            self.translator.translate(["ok"], LANGS[lang]["nllb"], beam_size=1)
        except Exception:
            pass

    def _wait_job(self, timeout: float = 30.0) -> None:
        if self._job is not None:
            try:
                self._job.result(timeout=timeout)
            except Exception:
                pass
            self._job = None

    # ------------------ yakalama ------------------
    def _grab(self, capturer: ScreenCapturer, region: tuple) -> np.ndarray | None:
        x, y, w, h = region[:4]
        need_hide = (not self._overlay_excluded) and self._overlay_has_content and self.s.overlay_visible
        self._capture_requires_hide = need_hide
        if need_hide and self._overlay_handle and len(region)>=6:
            with self._lock:areas=list(self._overlay_areas)
            if areas:
                sx,sy=w/max(1,region[4]),h/max(1,region[5])
                physical=[(a*sx,b*sy,c*sx,d*sy) for a,b,c,d in areas]
                image=capturer.grab_under_overlay(x,y,w,h,self._overlay_handle,physical)
                if image is not None:
                    self._capture_requires_hide = False
                    return image
        if need_hide:
            self._hide_ack.clear()
            self.hide_request.emit(True)
        try:
            if need_hide:
                if not self._hide_ack.wait(0.5):
                    # Never OCR our own translations if the UI did not hide in time.
                    return None
                time.sleep(0.06)
            return capturer.grab(x, y, w, h)
        finally:
            if need_hide:
                self.hide_request.emit(False)

    def _poll_interval_ms(self) -> int:
        interval = max(20, int(self.s.poll_ms))
        if getattr(self, '_capture_requires_hide', not self._overlay_excluded):
            return max(400, interval)
        return interval

    # ------------------ OCR işi (ayrı thread) ------------------
    def _ocr_job(self, crop: np.ndarray, top: int, gen: int, lang: str, beam: int,
                 context=_CONTEXT_UNSET, viewport: tuple[int, int] | None = None):
        t_start = time.perf_counter()
        ocr_t = tr_t = 0.0
        n = 0
        ch = crop.shape[0]
        keep_top, keep_bottom = top, top + ch
        src = LANGS[lang]["nllb"]
        if context is _CONTEXT_UNSET:
            context = self._session_context.fork() if self._context_enabled else None
        chunk_n = max(1, int(self.s.translate_chunk))
        # English balloons remain independent inputs, but may share a model
        # batch across panel boundaries. Other languages keep panel batches.
        pending = []
        diagnostic = {"language": lang, "via_english": self.s.chinese_translation_via_english,
                      "size": [crop.shape[1], ch], "stage": "ocr", "blocks": [],
                      "translated": 0, "empty_translations": 0}
        self._write_scan_diagnostic(diagnostic)

        true_edges = {'left', 'right'}
        if viewport is None or top <= viewport[0]:
            true_edges.add('top')
        if viewport is None or top + ch >= viewport[1]:
            true_edges.add('bottom')
        diagnostic["viewport_edges"] = sorted(true_edges)
        needs_full_retry = False
        it = self.ocr.process_iter(crop, EDGE_PX, frozenset(true_edges))
        while True:
            ta = time.perf_counter()
            finished = False
            try:
                batch = next(it)
            except StopIteration:
                finished = True
                batch = []
            ocr_t += time.perf_counter() - ta
            if gen != self._gen:
                return gen, None, None                         # sayfa değişti -> iptal

            kept = []
            for b in batch:
                diagnostic["blocks"].append({"box": [b.x1, b.y1, b.x2, b.y2],
                                             "cut": b.cut, "cut_edges": sorted(b.cut_edges),
                                             "panel": b.panel})
                if b.cut:
                    edges = b.cut_edges or frozenset(('top',) if b.cut_top or b.y1 <= EDGE_PX
                                                     else ('bottom',))
                    if 'top' in edges:
                        keep_top = max(keep_top, top + b.y2 + 1)
                    if 'bottom' in edges:
                        keep_bottom = min(keep_bottom, top + b.y1 - 1)
                    if ('top' in edges and 'top' not in true_edges or
                            'bottom' in edges and 'bottom' not in true_edges):
                        needs_full_retry = True
                else:
                    kept.append(b)

            if lang == "en":
                pending.extend(kept)
                ready = len(pending) if finished else len(pending) // chunk_n * chunk_n
                kept, pending = pending[:ready], pending[ready:]

            for i in range(0, len(kept), chunk_n):
                part = kept[i:i + chunk_n]
                ta = time.perf_counter()
                diagnostic["stage"] = "translation"
                self._write_scan_diagnostic(diagnostic)
                trs = self.translator.translate(
                    [b.text for b in part], src, beam_size=beam,
                    via_english=self.s.chinese_translation_via_english,
                    **({'context': context} if context is not None else {}),
                )
                if gen != self._gen:
                    return gen, None, None
                if len(trs) != len(part):
                    raise RuntimeError("Çeviri modeli tüm balonlar için sonuç döndürmedi.")
                if any(not t or not t.strip() for t in trs):
                    diagnostic["empty_translations"] += sum(not t or not t.strip() for t in trs)
                    self._write_scan_diagnostic(diagnostic)
                    raise RuntimeError("Çeviri modeli okunmuş bir balon için boş sonuç döndürdü.")
                tr_t += time.perf_counter() - ta
                items = []
                for b, t in zip(part, trs):
                    if not t:
                        diagnostic["empty_translations"] += 1
                        continue
                    c = crop[b.y1:b.y2, b.x1:b.x2]
                    if context is not None:
                        context.remember(b.text, t, src, panel=b.panel)
                    bg = tuple(int(v) for v in np.median(c.reshape(-1, 3), axis=0)) if c.size else (255, 255, 255)
                    items.append({"x": b.x1, "y": top + b.y1, "w": b.x2 - b.x1, "h": b.y2 - b.y1,
                                  "text": t, "src": b.text, "bg": bg, "vertical": b.vertical,
                                  "source_lang": lang, "panel": b.panel})
                n += len(items)
                diagnostic["translated"] = n
                if items:
                    self._partials.put((gen, items))
                    self._partial_ready.set()
                if gen != self._gen:
                    return gen, None, None

            if finished:
                break

        total = time.perf_counter() - t_start
        diagnostic["stage"] = "complete"
        diagnostic["elapsed_ms"] = round(total * 1000)
        diagnostic["ocr_ms"] = round(ocr_t * 1000)
        diagnostic["translation_ms"] = round(tr_t * 1000)
        self._write_scan_diagnostic(diagnostic)
        if gen == self._gen:
            self._job_full_retry = needs_full_retry
        self.status.emit(f"{n} balon  •  toplam {total*1000:.0f} ms  "
                         f"(OCR {ocr_t*1000:.0f} ms, çeviri {tr_t*1000:.0f} ms, şerit {ch}px)")
        return gen, keep_top, keep_bottom

    def _drain_partials(self) -> None:
        changed = False
        while True:
            try:
                gen, items = self._partials.get_nowait()
            except queue.Empty:
                break
            if gen != self._gen:
                continue
            for it in items:
                overlaps = [e for e in self.content_blocks if _overlap_ratio(it, e) > 0.5]
                if overlaps:
                    # Never let a broad OCR box collapse neighboring passages.
                    if len(overlaps) != 1 or not _more_complete(it, overlaps[0]):
                        continue
                    index = self.content_blocks.index(overlaps[0])
                    self.content_blocks[index] = it
                else:
                    self.content_blocks.append(it)
                if self._context_enabled:
                    self._session_context.remember(it['src'], it['text'], LANGS[it['source_lang']]['nllb'], panel=it.get('panel'))
                changed = True
        if len(self.content_blocks) > MAX_BLOCKS:
            self.content_blocks = self.content_blocks[-MAX_BLOCKS:]
        if changed:
            self._emit_visible()

    def _wait_for_next_frame(self, seconds: float) -> None:
        # Deliver completed translations while preserving the next capture deadline.
        deadline = time.monotonic() + seconds
        while self._running:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._partial_ready.wait(remaining):
                return
            self._partial_ready.clear()
            self._drain_partials()

    def _check_job(self) -> None:
        if self._job is None or not self._job.done():
            return
        job, self._job = self._job, None
        try:
            gen, kt, kb = job.result()
        except Exception as e:
            traceback.print_exc()
            self._job_failures += 1
            diagnostic = getattr(self, '_last_scan_diagnostic', None)
            if diagnostic is not None:
                diagnostic['failed_stage'] = diagnostic['stage']
                diagnostic['stage'] = 'failed'
                diagnostic['error'] = str(e)
                self._write_scan_diagnostic(diagnostic)
            # Two bounded retries; keep already displayed balloons (the overlap
            # filter deduplicates them) and never mark the failed scan processed.
            retry = self._job_failures <= 2
            if retry:
                self._attempted_scroll = None
                self._retry_after = time.monotonic() + 1.0
            self.status.emit(f"Hata: {e}" + (" — yeniden denenecek" if retry else " — Tek çevir ile tekrar deneyin"))
            return
        self._job_failures = 0
        self._drain_partials()
        if gen == self._gen and kt is not None and kb > kt:
            self.processed = _merge_intervals(self.processed + [[kt, kb]])
        if gen == self._gen and self._job_full_retry:
            self._retry_full_viewport = True
            self._attempted_scroll = None
        self._job_full_retry = False

    def _maybe_submit(self, img: np.ndarray, lang: str, force: bool) -> None:
        if self._job is not None:
            return
        if not force and time.monotonic() < self._retry_after:
            return
        if not force and self._attempted_scroll == self.scroll_y:
            return
        if self._attempted_scroll is not None and self._attempted_scroll != self.scroll_y:
            self._job_failures = 0
        self._attempted_scroll = self.scroll_y
        H = img.shape[0]
        vp = (self.scroll_y, self.scroll_y + H)
        missing = _subtract(vp, self.processed)
        if not missing and not self._retry_full_viewport:
            return
        if self._retry_full_viewport:
            a, b = vp
            self._retry_full_viewport = False
        else:
            a = max(vp[0], missing[0][0] - STRIP_MARGIN)
            b = min(vp[1], missing[-1][1] + STRIP_MARGIN)
        if self.s.bubble_detection and (a, b) != vp:
            # A 48px scroll margin can slice a three-line Korean balloon into
            # separate inputs. Expand the strip to whole visible balloons,
            # without a second OCR/model pass or a full-viewport rescan.
            from .bubbles import detect_bubbles
            bubbles = detect_bubbles(img, self.s.bubble_min_area)
            changed = True
            while changed:
                changed = False
                for balloon in bubbles:
                    y1, y2 = self.scroll_y + balloon.y1, self.scroll_y + balloon.y2
                    if y1 < b and y2 > a:
                        na, nb = min(a, max(vp[0], y1 - 8)), max(b, min(vp[1], y2 + 8))
                        if (na, nb) != (a, b):
                            a, b, changed = na, nb, True
        if b - a < 24:
            return
        crop = np.ascontiguousarray(img[a - self.scroll_y:b - self.scroll_y])
        self.status.emit("Okunuyor…")
        context = self._session_context.fork() if self._context_enabled else None
        self._job = self._executor.submit(self._ocr_job, crop, a, self._gen, lang,
                                          self.s.beam_size, context, vp)

    # ------------------ ana döngü ------------------
    @Slot()
    def run(self) -> None:
        try:
            self._load_translator()
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
            return

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        capturer = ScreenCapturer()
        prev_gray = prev_th = None
        last_motion = time.monotonic()
        seen_rver = -1
        was_active = False
        seen_context_version = 0

        while True:
            with self._lock:
                running, active, force = self._running, self._active, self._force
                region, lang, engine, over, rver = (self._region, self._lang, self._ocr_engine,
                                                    self._ocr_version, self._region_version)
                context_version = self._context_version
            if not running:
                break

            try:
                if context_version != seen_context_version:
                    seen_context_version = context_version
                    self._reset_content()
                    self._wait_job()
                    self._clear_translation_context()
                    prev_gray = None
                    last_motion = time.monotonic()
                if (lang != self._loaded_lang or engine != self._loaded_ocr_engine
                        or over != self._loaded_ocr_version):
                    self._reset_content()
                    self._wait_job()
                    if lang != self._loaded_lang:
                        self._clear_translation_context()
                    self._load_ocr(lang)
                    prev_gray = None
                    last_motion = time.monotonic()

                if region is None or (not active and not force):
                    if was_active:
                        self._reset_content()
                        was_active = False
                    prev_gray = None
                    time.sleep(0.1)
                    continue
                was_active = True

                if rver != seen_rver:
                    seen_rver = rver
                    self._reset_content()
                    self._wait_job()
                    self._clear_translation_context()
                    prev_gray = None
                    last_motion = time.monotonic()

                loop_start = time.perf_counter()
                img = self._grab(capturer, region)
                if img is None:
                    time.sleep(0.2)
                    continue
                gray = to_gray(img)
                th = thumbnail_gray(gray)
                self._H = img.shape[0]
                self._sx = img.shape[1] / max(1, region[4])
                self._sy = img.shape[0] / max(1, region[5])
                now = time.monotonic()

                if prev_gray is not None:
                    if prev_gray.shape != gray.shape:
                        self._reset_content()
                        last_motion = now
                    else:
                        dy = (estimate_vshift(prev_gray, gray, self.s.change_threshold)
                              if self.s.scroll_tracking else None)
                        if dy:   # kaydırma -> çevirileri içerikle birlikte kaydır
                            self.scroll_y += dy
                            last_motion = now
                            self._emit_visible()
                        elif frame_diff(th, prev_th) > self.s.change_threshold:
                            self._reset_content()      # sayfa değişti
                            last_motion = now
                prev_gray, prev_th = gray, th

                self._drain_partials()
                self._check_job()

                if force:
                    if self._job is None:
                        self._reset_content()
                        self._maybe_submit(img, lang, True)
                        with self._lock:
                            self._force = False
                elif (now - last_motion) * 1000 >= self.s.settle_ms:
                    self._maybe_submit(img, lang, False)

                poll = self._poll_interval_ms()
                elapsed = time.perf_counter() - loop_start
                self._wait_for_next_frame(max(0.005, poll / 1000 - elapsed))

            except Exception as e:
                traceback.print_exc()
                self.status.emit(f"Hata: {e}")
                time.sleep(1.0)

        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
        if self.translator is not None:
            self.translator.close()
        if self.ocr is not None:
            self.ocr.close()
        self._session_context.clear()
        capturer.close()
