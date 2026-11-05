"""
Gömülü OCR motoru.
- Tüm diller: PaddleOCR ile bölge tespiti ve balon gruplama.
- Japonca: isteğe bağlı izole manga-ocr tanıması (CPU / GPU).
process_iter() sonuçları parça parça (yukarıdan aşağı) üretir -> ekrana aşamalı basılır.
"""
from __future__ import annotations

import os
import re
import unicodedata
import json
from dataclasses import dataclass
from typing import Iterator

import numpy as np
from PIL import Image

from ..config import LANGS, Settings
from .textgroup import Box, bbox_of, group_boxes, order_boxes
from .ocr_budget import PredictionBudget
from .bubbles import bubble_id, detect_bubbles, open_white_edge, shift_bubbles
from .panels import detect_panels, panel_id, order_by_panel


@dataclass
class OCRBlock:
    x1: int
    y1: int
    x2: int
    y2: int
    text: str
    vertical: bool = False
    cut: bool = False   # görüntü kenarına değiyor (yarım balon) -> okunmadı
    cut_top: bool = False
    panel: int | None = None
    cut_edges: frozenset[str] = frozenset()
    confidence: float | None = None
    balloon: bool = False


def resolve_gpu(setting: str) -> bool:
    if setting == "no":
        return False
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        # Gerçek bir işlem dene: yanlış torch sürümünde (ör. RTX 50 + cu124)
        # "no kernel image is available" hatası burada yakalanır.
        (torch.ones(16, device="cuda") * 2).sum().item()
        torch.backends.cudnn.benchmark = True
        return True
    except Exception as e:
        print(f"[ocr] GPU kullanılamıyor, CPU'ya geçiliyor: {e}\n"
              f"      RTX 50 serisi için: pip install torch --index-url "
              f"https://download.pytorch.org/whl/cu128")
        return False


# ----------------------------------------------------------------------
_BOUND_SUFFIXES = frozenset((
    "ing", "ed", "er", "est", "ly", "tion", "sion", "ment", "ness",
    "ful", "less", "able", "ible", "ous", "ive", "al", "ic", "ize",
    "ise", "ify", "ity",
))


def _resolve_hyphen_space(match: re.Match[str]) -> str:
    left, right = match.group(1), match.group(2)
    l_low, r_low = left.lower(), right.lower()
    if len(left) <= 2 and (r_low.startswith(l_low) or (l_low == "i" and r_low == "i")):
        return f"{left}-{right}"
    if r_low in _BOUND_SUFFIXES:
        return f"{left}{right}"
    return f"{left} - {right}"


def _sentence_case(text: str) -> str:
    t = text.lower()
    t = re.sub(
        r'(^|[.!?…]\s+)(["\'“‘(\[\-—…\s]*[a-z])',
        lambda m: m.group(1) + m.group(2).upper(),
        t,
    )
    t = re.sub(r"\bi\b", "I", t)
    t = re.sub(r"\bi'(m|ll|ve|d)\b", lambda m: "I'" + m.group(1), t)
    t = re.sub(
        r"\b(mr|mrs|ms|dr)\.\s+([A-Za-z])",
        lambda m: m.group(1).capitalize() + ". " + m.group(2).upper(),
        t,
    )
    return t


def clean_text(text: str, lang: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip()
    if lang in ("ja", "zh", "zh_tw"):
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[.・]{2,}", "…", text)
    else:
        if lang == "en":
            text = re.sub(r"(?<=[A-Za-z])[’‘`´](?=[A-Za-z])", "'", text)
            text = re.sub(
                r"\b([A-Za-z]+)\s*'\s*(t|s|m|re|ve|ll|d)\b",
                r"\1'\2",
                text,
                flags=re.I,
            )
            text = re.sub(r"([A-Za-z]+)-\s+([A-Za-z]+)", _resolve_hyphen_space, text)
        else:
            text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
        text = re.sub(r"(\.{3,}|…)(?=[A-Za-z\uac00-\ud7af])", r"\1 ", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.!?…])", r"\1", text)
        if lang == "en":
            letters = [c for c in text if c.isalpha()]
            if letters and sum(c.isupper() for c in letters) / len(letters) > 0.7:
                text = _sentence_case(text)
    return text.strip()


def is_meaningful(text: str, lang: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    if lang == "en" and len(letters) < 2:
        return False
    return True


# ----------------------------------------------------------------------
class OCREngine:
    def __init__(self, lang: str, settings: Settings) -> None:
        self.lang = lang
        self.info = LANGS[lang]
        self.s = settings
        self.gpu = False
        self.engine_preference = settings.ocr_engine
        self.reader = None

        self.manga = None
        self.paddle = None
        # Paddle ve izole manga-ocr farklı CUDA çalışma zamanları kullanabilir.
        # Bu değer durum çubuğunda gerçek cihazı göstermek için tutulur.
        self.paddle_device: str | None = None
        self.paddle_model_kind: str | None = None
        self.manga_warning = ''
        if settings.ocr_backend != 'local':
            from .runtime_client import RuntimeClient
            self.paddle = RuntimeClient('ocr', settings.ocr_backend, language=lang,
                canvas=settings.ocr_canvas_size, paddle_mobile=settings.paddle_mobile)
            self.paddle_device = self.paddle.device
            self.paddle_model_kind = ('Mobil · izole' if settings.paddle_mobile
                                      else 'Sunucu · izole')
            self.gpu = settings.ocr_backend != 'cpu'
        want_paddle = lang in LANGS and settings.ocr_backend == 'local'
        if want_paddle:
            try:
                import paddle
                from paddleocr import PaddleOCR
                # Paddle ve PyTorch GPU paketleri Windows'ta farklı CUDA
                # çalışma zamanları kullanabilir. Paddle'ın cihaz seçimini
                # PyTorch'un CUDA durumundan bağımsız tutuyoruz.
                paddle_device = (
                    "gpu:0"
                    if settings.use_gpu != "no" and paddle.is_compiled_with_cuda()
                    else "cpu"
                )
                self.paddle_device = paddle_device
                self.paddle_model_kind = "Mobil" if settings.paddle_mobile else "Sunucu"
                paddle_models = {
                    'text_detection_model_name': ('PP-OCRv5_mobile_det' if settings.paddle_mobile
                                                  else 'PP-OCRv5_server_det'),
                    'text_recognition_model_name': ('PP-OCRv5_mobile_rec' if settings.paddle_mobile
                                                    else 'PP-OCRv5_server_rec'),
                }
                if lang == 'ko':
                    paddle_models = {
                        'text_detection_model_name': 'PP-OCRv5_mobile_det' if settings.paddle_mobile else 'PP-OCRv5_server_det',
                        'text_recognition_model_name': 'korean_PP-OCRv5_mobile_rec',
                    }
                    if not settings.paddle_mobile:
                        self.paddle_model_kind = 'Sunucu tespit / Mobil Korece'
                self.paddle = PaddleOCR(
                    lang={"zh_tw": "chinese_cht", "ja": "japan", "en": "en", "ko": "korean"}.get(lang, "ch"),
                    ocr_version="PP-OCRv5",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    # The generic 0/180 classifier can invert upright Hangul.
                    # Korean webtoon dialogue is horizontal; preserve its direction.
                    use_textline_orientation=lang != 'ko',
                    text_det_limit_side_len=max(1280, settings.ocr_canvas_size),
                    text_det_limit_type="max",
                    text_det_box_thresh=0.35,
                    text_rec_score_thresh=0.12,
                    device=paddle_device,
                    # Paddle 3.3 + Windows oneDNN'de bazı model öznitelikleri için
                    # çalışma zamanı hatası oluşuyor; standart Paddle motoru kararlı.
                    enable_mkldnn=False,
                    **paddle_models,
                )
            except Exception as e:
                self.paddle_device = None
                self.paddle_model_kind = None
                raise RuntimeError(f'PaddleOCR yüklenemedi. bagliliklar.bat ile Paddle kurulumunu kontrol edin: {e}') from e

        want_manga = lang == 'ja' and (self.engine_preference == 'manga_ocr'
            or (settings.use_manga_ocr and self.engine_preference == 'auto'))
        if want_manga:
            from .manga_client import MangaClient
            from .runtime_client import RuntimeClient
            device = 'cpu' if settings.use_gpu == 'no' else settings.manga_device
            try:
                self.manga = (RuntimeClient('manga', settings.manga_backend)
                              if settings.manga_backend != 'local' else MangaClient(device))
            except Exception as exc:
                self.manga_warning = str(exc)
                if device == 'auto':
                    try:
                        self.manga = MangaClient('cpu')
                        self.manga_warning = f'GPU başlatılamadı; manga-ocr CPU: {exc}'
                    except Exception:
                        pass
                print(f'[ocr] Manga yardımcı işlem: {self.manga_warning}')
            self.gpu = self.manga is not None and self.manga.device.startswith(('cuda','gpu','xpu'))

    def close(self):
        if self.manga is not None:
            self.manga.close()
            self.manga = None
        if hasattr(self.paddle, "close"):
            self.paddle.close()
        self.paddle = None

    # ------------------------------------------------------------------
    def process_iter(self, rgb: np.ndarray, edge_px: int = 3,
                     viewport_edges: frozenset[str] = frozenset(('top', 'bottom', 'left', 'right')),
                     bubbles: list | None = None
                     ) -> Iterator[list[OCRBlock]]:
        panels = detect_panels(rgb)
        if self.manga is not None:
            yield from self._iter_paddle_manga(rgb, edge_px, panels, viewport_edges, bubbles=bubbles)
        elif self.paddle is not None:
            blocks = self._process_paddle(rgb, edge_px, panels, viewport_edges, bubbles=bubbles)
            if blocks:
                yield from self._panel_batches(blocks, panels)

    def _panel_batches(self, blocks, panels):
        batch = []
        previous = object()
        for b in order_by_panel(blocks, panels, self.info['vertical_rtl']):
            b.panel = panel_id(b, panels)
            if batch and b.panel != previous:
                yield batch
                batch = []
            batch.append(b)
            previous = b.panel
        if batch:
            yield batch

    def _layout_groups(self, boxes, bubbles, panels):
        # Split/retry passes can rediscover the same column. Keep the strongest
        # spatially overlapping copy, never remove repetitions elsewhere.
        unique = []
        for b in sorted(boxes, key=lambda b: -b.conf):
            duplicate = False
            b_clean = clean_text(b.text, self.lang)
            b_norm = re.sub(r'\W+', '', b_clean).casefold()
            for old in unique:
                overlap = max(0, min(b.x2, old.x2)-max(b.x1, old.x1)) * max(0, min(b.y2, old.y2)-max(b.y1, old.y1))
                min_area = min(b.w*b.h, old.w*old.h)
                old_clean = clean_text(old.text, self.lang)
                if b_clean == old_clean and overlap > .45 * min_area:
                    duplicate = True
                    break
                if overlap > .60 * min_area and len(b_norm) >= 2:
                    old_norm = re.sub(r'\W+', '', old_clean).casefold()
                    if b_norm in old_norm or (len(old_norm) >= 2 and old_norm in b_norm):
                        duplicate = True
                        break
            if not duplicate:
                unique.append(b)
        ids = [bubble_id(b, bubbles, .75 if self.lang in ('ja','en') else 0.0,
                         interior_coverage=.50 if self.lang == 'en' else None)
               for b in unique] if bubbles else None
        pids = [panel_id(b, panels) for b in unique] if panels else None
        if pids is not None and panels:
            for i, b in enumerate(unique):
                if pids[i] is not None or b.vertical:
                    continue
                overlapped = [
                    idx_p for idx_p, p in enumerate(panels)
                    if max(0, min(b.x2, p.x2) - max(b.x1, p.x1))
                    * max(0, min(b.y2, p.y2) - max(b.y1, p.y1)) >= .50 * b.w * b.h
                ]
                if len(overlapped) == 1:
                    cand_p = overlapped[0]
                    if any(
                        pids[j] == cand_p and not other.vertical
                        and max(0, min(b.x2, other.x2) - max(b.x1, other.x1)) / max(1, min(b.w, other.w)) > .45
                        and max(0, max(b.y1, other.y1) - min(b.y2, other.y2)) <= max(b.char_size, other.char_size) * self.s.group_gap_ratio
                        for j, other in enumerate(unique)
                    ):
                        pids[i] = cand_p
        if self.lang == 'en' and ids is not None and bubbles:
            changed = True
            while changed:
                changed = False
                for i, b in enumerate(unique):
                    if ids[i] is not None or b.vertical:
                        continue
                    raw_bid = bubble_id(b, bubbles, 0.0)
                    for j, other in enumerate(unique):
                        cand = ids[j]
                        if cand is None or other.vertical:
                            continue
                        if raw_bid not in (None, cand):
                            continue
                        if pids is not None and pids[i] != pids[j] and pids[i] is not None and pids[j] is not None:
                            continue
                        bub = bubbles[cand]
                        if b.x1 < bub.x1 - b.char_size or b.x2 > bub.x2 + b.char_size:
                            continue
                        ca, cb = b.char_size, other.char_size
                        if max(ca, cb) / max(1, min(ca, cb)) > 1.6:
                            continue
                        xo = max(0, min(b.x2, other.x2) - max(b.x1, other.x1)) / max(1, min(b.w, other.w))
                        vgap = max(0, max(b.y1, other.y1) - min(b.y2, other.y2))
                        if xo > .45 and vgap <= max(ca, cb) * self.s.group_gap_ratio:
                            ids[i] = cand
                            changed = True
                            break
        if self.lang == 'en' and ids is not None:
            # A verified balloon is one passage even with ragged centering,
            # generous leading or a short last word. Never relax geometry for
            # unknown/scenery boxes, and never join across two distinct panels.
            # A line straddling a false gutter inside the same balloon (panel None)
            # follows the nearest assigned line in that balloon so non-adjacent
            # unassigned lines never merge around a middle line.
            assigned_panels = {}
            if pids is not None:
                for idx_b, (bid, pid) in enumerate(zip(ids, pids)):
                    if bid is not None and pid is not None:
                        assigned_panels.setdefault(bid, []).append((unique[idx_b].cy, pid))
            paragraphs = {}
            unknown = []
            for i, bid in enumerate(ids):
                box = unique[i]
                pid = pids[i] if pids is not None else None
                if pid is None and bid in assigned_panels:
                    pid = min(assigned_panels[bid], key=lambda item: abs(box.cy - item[0]))[1]
                short_latin = (bool(re.fullmatch(r'[A-Za-z]{1,3}[.!?]?', box.text.strip()))
                    and any(not other.vertical and box.h <= other.h * 1.5
                            and ids[j] == bid
                            and (pids is None or pids[j] == pid or pids[j] is None)
                            for j, other in enumerate(unique)))
                if bid is None or (box.vertical and not short_latin):
                    unknown.append(i)
                else:
                    key = (bid, pid)
                    paragraphs.setdefault(key, []).append(box)
            remaining = [unique[i] for i in unknown]
            remaining_panels = [pids[i] for i in unknown] if pids is not None else None
            # Preserve the original center-based isolation for fallback geometry
            # (notably vertical/outline columns); coverage cannot relax it.
            remaining_ids = [bubble_id(b, bubbles) for b in remaining] if bubbles else None
            # A short word ("I", "A") split onto the start of a horizontal line
            # can have h > 1.5*w. Widen a proxy only when a horizontal neighbor
            # shares the same baseline, never for vertical columns.
            proxies = []
            for idx, b in enumerate(remaining):
                if (b.vertical and bool(re.fullmatch(r'[A-Za-z]{1,3}[.!?]?', b.text.strip()))
                        and any(k != idx and other.w > other.h * 1.5
                                and (remaining_ids is None or remaining_ids[k] == remaining_ids[idx])
                                and (remaining_panels is None or remaining_panels[k] == remaining_panels[idx])
                                and max(0, min(b.y2, other.y2) - max(b.y1, other.y1)) >= 0.6 * min(b.h, other.h)
                                and max(0, max(b.x1, other.x1) - min(b.x2, other.x2)) <= max(b.h, other.h) * self.s.group_gap_ratio
                                for k, other in enumerate(remaining))):
                    proxies.append(Box(b.x1, b.y1, max(b.x2, b.x1 + b.h), b.y2, b.text, b.conf))
                elif (b.w > b.h * 1.5 and any(
                        k != idx and other.w > other.h * 1.5
                        and (remaining_ids is None or remaining_ids[k] == remaining_ids[idx])
                        and (remaining_panels is None or remaining_panels[k] == remaining_panels[idx])
                        and max(b.h, other.h) / max(1, min(b.h, other.h)) <= 1.4
                        and max(0, min(b.x2, other.x2) - max(b.x1, other.x1)) / max(1, min(b.w, other.w)) >= 0.55
                        and 0 < other.y1 - b.y2 <= max(b.h, other.h) * 0.85
                        for k, other in enumerate(remaining))):
                    proxies.append(Box(b.x1, b.y1, b.x2, b.y2 + max(2, int(b.h * 0.20)), b.text, b.conf))
                else:
                    proxies.append(b)
            geometric = group_boxes(proxies, self.s.group_gap_ratio,
                                    bubble_ids=remaining_ids, panel_ids=remaining_panels)
            return list(paragraphs.values()) + [[remaining[i] for i in g] for g in geometric]
        if self.lang == 'en' and not bubbles:
            proxies = []
            for idx, b in enumerate(unique):
                if (b.vertical and bool(re.fullmatch(r'[A-Za-z]{1,3}[.!?]?', b.text.strip()))
                        and any(k != idx and other.w > other.h * 1.5
                                and (pids is None or pids[k] == pids[idx])
                                and max(0, min(b.y2, other.y2) - max(b.y1, other.y1)) >= 0.6 * min(b.h, other.h)
                                and max(0, max(b.x1, other.x1) - min(b.x2, other.x2)) <= max(b.h, other.h) * self.s.group_gap_ratio
                                for k, other in enumerate(unique))):
                    proxies.append(Box(b.x1, b.y1, max(b.x2, b.x1 + b.h), b.y2, b.text, b.conf))
                elif (b.w > b.h * 1.5 and any(
                        k != idx and other.w > other.h * 1.5
                        and (pids is None or pids[k] == pids[idx])
                        and max(b.h, other.h) / max(1, min(b.h, other.h)) <= 1.4
                        and max(0, min(b.x2, other.x2) - max(b.x1, other.x1)) / max(1, min(b.w, other.w)) >= 0.55
                        and 0 < other.y1 - b.y2 <= max(b.h, other.h) * 0.85
                        for k, other in enumerate(unique))):
                    proxies.append(Box(b.x1, b.y1, b.x2, b.y2 + max(2, int(b.h * 0.20)), b.text, b.conf))
                else:
                    proxies.append(b)
            return [[unique[i] for i in g] for g in group_boxes(
                proxies, self.s.group_gap_ratio, None, pids)]
        if self.lang == 'ko' and pids is not None and ids is not None:
            assigned_ko = {}
            for bid, pid in zip(ids, pids):
                if bid is not None and pid is not None:
                    assigned_ko.setdefault(bid, set()).add(pid)
            pids = [next(iter(assigned_ko[bid]))
                    if pid is None and bid in assigned_ko and len(assigned_ko[bid]) == 1 else pid
                    for bid, pid in zip(ids, pids)]
        return [[unique[i] for i in g] for g in group_boxes(
            unique, self.s.group_gap_ratio, ids, pids,
            same_bubble_gap_ratio=1.25 if self.lang == 'ko' else None,
            allow_short_bubble_columns=self.lang == 'ja')]

    @staticmethod
    def _cut_region(x1, y1, x2, y2, W, H, edge, members, bubbles,
                    min_coverage=0.0, rgb=None, viewport_edges=frozenset(('top', 'bottom', 'left', 'right'))):
        edges = set()
        if x1 <= edge:
            edges.add('left')
        if y1 <= edge:
            edges.add('top')
        if x2 >= W-edge:
            edges.add('right')
        if y2 >= H-edge:
            edges.add('bottom')
        # Text may be fully visible while its enclosing balloon is clipped.
        # Ignore large scene-background candidates from the bubble detector.
        has_verified_balloon = False
        for member in members:
            bid = bubble_id(member, bubbles, min_coverage,
                            interior_coverage=.50 if min_coverage >= .75 else None)
            if bid is None:
                continue
            b = bubbles[bid]
            area = (b.x2-b.x1)*(b.y2-b.y1)
            if area > max(1, (x2-x1)*(y2-y1))*12 and (
                    b.x2 - b.x1 > W * 0.70 or b.y2 - b.y1 > H * 0.85):
                continue
            if area > W*H*.35 and (b.x2 - b.x1 > W * 0.65 and b.y2 - b.y1 > H * 0.65):
                continue
            has_verified_balloon = True
            touches = False
            if b.x1 <= edge:
                edges.add('left')
                touches = True
            if b.y1 <= edge:
                edges.add('top')
                touches = True
            if b.x2 >= W-edge:
                edges.add('right')
                touches = True
            if b.y2 >= H-edge:
                edges.add('bottom')
                touches = True
            if touches:
                y1, y2 = min(y1, max(0, b.y1)), max(y2, min(H, b.y2))
        if not has_verified_balloon and members and not all(m.vertical for m in members):
            # Without a closed balloon contour, a horizontal line sitting less than
            # one line-height from a true top/bottom viewport edge is very likely a
            # half-visible balloon whose remaining lines are still off-screen.
            line_h = max(1, min((b.char_size for b in members), default=y2 - y1))
            margin = max(edge, min(28, int(line_h * 0.75)))
            if 'top' in viewport_edges and y1 <= margin:
                edges.add('top')
            if 'bottom' in viewport_edges and H - y2 <= margin:
                edges.add('bottom')
        if rgb is not None:
            group = Box(x1, y1, x2, y2)
            for side in viewport_edges:
                probe = group
                if side in ('top', 'bottom'):
                    # A single visible line can sit above a clipped balloon's
                    # remaining lines. Probe one line farther inward, retaining
                    # the image-level curved/compact open-balloon checks.
                    line = max(1, min((b.char_size for b in members), default=group.h))
                    probe = Box(x1, max(0, y1-line) if side == 'bottom' else y1,
                                x2, min(H, y2+line) if side == 'top' else y2)
                if side not in edges and open_white_edge(rgb, probe, side):
                    edges.add(side)
        return bool(edges), 'top' in edges, y1, y2, frozenset(edges)

    def process(self, rgb: np.ndarray) -> list[OCRBlock]:
        return [b for batch in self.process_iter(rgb) for b in batch]

    def reset_scan(self):
        """Begin an explicitly fresh strip, even when its pixels are identical."""
        self._prediction_budget = None
        self.last_predict_count = 0
        self.has_pending_retries = False
        self.pending_retry_count = 0

    def _predict(self, rgb, primary=False):
        budget = getattr(self, '_prediction_budget', None)
        if budget is None:
            budget = self._prediction_budget = PredictionBudget()
        try:
            return budget.predict(self.paddle.predict, rgb, primary=primary)
        finally:
            self.last_predict_count = budget.used
            self.has_pending_retries = bool(budget.pending)
            self.pending_retry_count = len(budget.pending)

    def _process_paddle(self, rgb: np.ndarray, edge: int, panels=None,
                        viewport_edges=frozenset(('top', 'bottom', 'left', 'right')),
                        finish_budget=True, bubbles=None) -> list[OCRBlock]:
        """PP-OCR v3/v5 sonuçlarını sürümden bağımsız şekilde OCRBlock'a dönüştürür."""
        H, W = rgb.shape[:2]
        budget = getattr(self, '_prediction_budget', None)
        if budget is None:
            budget = self._prediction_budget = PredictionBudget()
        budget.begin(rgb)
        self.last_predict_count = 0
        self.has_pending_retries = False
        self.pending_retry_count = 0
        if not self.s.bubble_detection:
            bubbles = []
        elif bubbles is None:
            bubbles = detect_bubbles(rgb, self.s.bubble_min_area)
        else:
            local = detect_bubbles(rgb, self.s.bubble_min_area)
            bubbles = list(bubbles) + [
                b for b in local
                if not any(max(0, min(b.x2, e.x2)-max(b.x1, e.x1)) *
                           max(0, min(b.y2, e.y2)-max(b.y1, e.y1)) >
                           0.7 * min(max(1, (b.x2-b.x1)*(b.y2-b.y1)),
                                     max(1, (e.x2-e.x1)*(e.y2-e.y1)))
                           for e in bubbles)]
        try:
            result = self._predict(rgb, primary=True)
            data = getattr(result, "json", result)
            if isinstance(data, str):
                data = json.loads(data)
            # PaddleOCR sürümleri alanları doğrudan veya "res" altında döndürebilir.
            data = data.get("res", data) if isinstance(data, dict) else {}
            if self.lang == 'ja':
                # White outlines and screen tones often form tiny false balloons.
                # Do not use them for splitting, grouping or clipped-balloon tests.
                raw_boxes = [Box(*self._clamp(*r, W, H))
                             for r, t in zip(data.get('rec_boxes', []), data.get('rec_texts', []))
                             if is_meaningful(str(t), self.lang)]
                bubbles = [b for b in bubbles if any(
                    bubble_id(r, [b], .75) is not None for r in raw_boxes
                    if min(r.w, r.h) >= self.s.min_box_size)]
            data = self._split_paddle_bubble_regions(rgb, data, bubbles)
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            rects = data.get("rec_boxes", [])
        except Exception as e:
            # A failed prediction is not a successfully scanned empty page.
            # Let the worker retain the unprocessed interval and retry it.
            raise RuntimeError(f"PaddleOCR okuma hatası: {e}") from e

        boxes: list[Box] = []
        weak_boxes: list[Box] = []
        for rect, text, score in zip(rects, texts, scores):
            if not text:
                continue
            x1, y1, x2, y2 = self._clamp(*rect, W, H)
            if min(x2 - x1, y2 - y1) >= self.s.min_box_size:
                box = Box(x1, y1, x2, y2, text=str(text), conf=float(score))
                if box.conf >= self.s.min_confidence:
                    boxes.append(box)
                if box.conf < 0.65:
                    weak_boxes.append(box)
        if self.lang in ("zh", "zh_tw", "ja"):
            self._retry_paddle_regions(rgb, boxes, weak_boxes)
        elif self.lang == "en" and bubbles:
            self._retry_english_bubbles(rgb, boxes, weak_boxes, bubbles, edge)
        panels = detect_panels(rgb) if panels is None else panels
        blocks: list[OCRBlock] = []
        group_cov = .75 if self.lang in ('ja', 'en') else 0.0
        group_int = .35 if self.lang == 'en' else None
        for group in self._layout_groups(boxes, bubbles, panels):
            members = order_boxes(group, self.info["vertical_rtl"])
            x1, y1, x2, y2 = bbox_of(members)
            vertical = sum(b.vertical for b in members) > len(members) / 2
            bids = {bubble_id(m, bubbles, group_cov, interior_coverage=group_int)
                    for m in members} if bubbles else {None}
            in_balloon = len(bids) == 1 and None not in bids
            cut, cut_top, y1, y2, cut_edges = self._cut_region(
                x1, y1, x2, y2, W, H, edge, members, bubbles,
                min_coverage=.75 if self.lang == 'ja' else 0.0,
                rgb=rgb, viewport_edges=viewport_edges)
            if cut:
                blocks.append(OCRBlock(x1, y1, x2, y2, "", vertical, cut=True,
                                       cut_top=cut_top, cut_edges=cut_edges,
                                       confidence=min(b.conf for b in members),
                                       balloon=in_balloon))
                continue
            text = clean_text(self.info["joiner"].join(b.text for b in members), self.lang)
            if is_meaningful(text, self.lang):
                blocks.append(OCRBlock(x1, y1, x2, y2, text, vertical,
                                       confidence=min(b.conf for b in members),
                                       balloon=in_balloon))
        if finish_budget:
            budget.finish()
        return blocks

    def _split_paddle_bubble_regions(self, rgb, data, bubbles):
        """Balon sınırından taşan OCR kutusunu iç/dış kırpımlarda yeniden oku."""
        if not bubbles:
            return data
        H, W = rgb.shape[:2]
        rows = list(zip(data.get("rec_boxes", []), data.get("rec_texts", []),
                        data.get("rec_scores", [])))
        out = []
        retried = 0
        for rect, text, score in rows:
            # Yüksek güvenli sütunları, sahnedeki yanlış balon adayları
            # nedeniyle yeniden parçalama. Kurtarma yalnızca şüpheli okumaya ait.
            if float(score) >= 0.80:
                out.append((rect, text, score))
                continue
            x1, y1, x2, y2 = self._clamp(*rect, W, H)
            area = max(1, (x2 - x1) * (y2 - y1))
            candidates = []
            for bubble in bubbles:
                intersection = max(0, min(x2, bubble.x2) - max(x1, bubble.x1)) * max(
                    0, min(y2, bubble.y2) - max(y1, bubble.y1))
                fraction = intersection / area
                # Çok küçük kesişme, normal algılama kenar payı veya panel
                # boyutundaki bölgeler için ek okuma yapma.
                if 0.2 < fraction < 0.80 and (bubble.x2 - bubble.x1) * (bubble.y2 - bubble.y1) < W * H * 0.35:
                    candidates.append(bubble)
            if not candidates:
                out.append((rect, text, score))
                continue
            bubble = min(candidates, key=lambda b: (b.x2 - b.x1) * (b.y2 - b.y1))
            regions = [(bubble.x1, bubble.y1, bubble.x2, bubble.y2),
                       (x1, y1, x2, min(y2, bubble.y1)),
                       (x1, max(y1, bubble.y2), x2, y2),
                       (x1, max(y1, bubble.y1), min(x2, bubble.x1), min(y2, bubble.y2)),
                       (max(x1, bubble.x2), max(y1, bubble.y1), x2, min(y2, bubble.y2))]
            recovered = []
            budget = getattr(self, '_prediction_budget', None)
            deferred_before = len(budget.pending) if budget is not None else 0
            inside_found = False
            retried += 1
            try:
                for index, (a, b, c, d) in enumerate(regions):
                    a, b, c, d = self._clamp(a, b, c, d, W, H)
                    if min(c - a, d - b) < 20:
                        continue
                    result = self._predict(np.ascontiguousarray(rgb[b:d, a:c]))
                    local = getattr(result, "json", result)
                    if isinstance(local, str):
                        local = json.loads(local)
                    local = local.get("res", local) if isinstance(local, dict) else {}
                    for r, t, confidence in zip(local.get("rec_boxes", []), local.get("rec_texts", []), local.get("rec_scores", [])):
                        if not is_meaningful(str(t), self.lang) or float(confidence) < max(0.85, self.s.min_confidence):
                            continue
                        lx1, ly1, lx2, ly2 = self._clamp(*r, c - a, d - b)
                        if min(lx2 - lx1, ly2 - ly1) < self.s.min_box_size:
                            continue
                        if index == 0:
                            inside_found = True
                        recovered.append(([a + lx1, b + ly1, a + lx2, b + ly2], str(t), float(confidence)))
            except Exception as e:
                print(f"[ocr] Balon sınırı yeniden okuması atlandı: {e}")
                inside_found = False
            # A partly scanned split must never discard the original row.
            budget = getattr(self, '_prediction_budget', None)
            if budget is not None and (len(budget.pending) > deferred_before or budget.failures):
                inside_found = False
            out.extend(recovered if inside_found else [(rect, text, score)])
        return {"rec_boxes": [r for r, t, s in out], "rec_texts": [t for r, t, s in out],
                "rec_scores": [s for r, t, s in out]}

    def _retry_english_bubbles(self, rgb, boxes, weak_boxes, bubbles, edge):
        """Recover missed English lines with the shared strip prediction budget.

        Uncovered letter-sized ink (or a low-confidence line) triggers one local
        OCR pass. Keep strong existing lines; never retry a clipped balloon or
        accept scenery outside its contour. A failed optional pass is harmless.
        """
        import cv2

        H, W = rgb.shape[:2]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        self.last_english_retry_count = 0
        self.last_english_recovered_count = 0
        for balloon in sorted(bubbles, key=lambda b: (b.y1, b.x1)):
            x1, y1, x2, y2 = balloon.x1, balloon.y1, balloon.x2, balloon.y2
            if (x1 <= edge or y1 <= edge or x2 >= W - edge or y2 >= H - edge
                    or (x2 - x1) * (y2 - y1) > W * H * .45):
                continue
            inside = [b for b in boxes if bubble_id(b, [balloon], .75) is not None]
            weak = [b for b in weak_boxes if bubble_id(b, [balloon], .75) is not None]
            mask = np.zeros((y2 - y1, x2 - x1), np.uint8)
            if balloon.contour is None:
                mask[:] = 255
            else:
                contour = balloon.contour - np.array([[[x1, y1]]], dtype=np.int32)
                cv2.drawContours(mask, [contour], -1, 255, -1)
            # Remove the balloon outline before looking for missing letters.
            mask = cv2.erode(mask, np.ones((9, 9), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)
            local_gray = gray[y1:y2, x1:x2]
            if not np.any(mask) or np.mean(local_gray[mask > 0] > 205) < .70:
                continue
            ink = ((local_gray < 160) & (mask > 0)).astype(np.uint8)
            for old in inside + weak:
                a, b, c, d = self._clamp(old.x1 - x1 - 3, old.y1 - y1 - 3,
                                         old.x2 - x1 + 3, old.y2 - y1 + 3,
                                         x2 - x1, y2 - y1)
                ink[b:d, a:c] = 0
            _, _, stats, centers = cv2.connectedComponentsWithStats(ink)
            letter_height = float(np.median([b.h for b in inside + weak])) if inside or weak else 24.0
            letters = [centers[i] for i, (_, _, w, h, area) in enumerate(stats[1:], 1)
                       if 3 <= h <= min(64, max(16, letter_height * 1.5))
                       and 2 <= w <= max(20, letter_height * 2) and area >= 6]
            # Three aligned components distinguish an unread line from speckles.
            missing_line = any(sum(abs(a[1] - b[1]) <= max(5, letter_height * .5)
                                   for b in letters) >= 3 for a in letters)
            if not weak and not missing_line:
                continue
            self.last_english_retry_count += 1
            try:
                result = self._predict(np.ascontiguousarray(rgb[y1:y2, x1:x2]))
                data = getattr(result, "json", result)
                if isinstance(data, str):
                    data = json.loads(data)
                data = data.get("res", data) if isinstance(data, dict) else {}
                for rect, text, score in zip(data.get('rec_boxes', []), data.get('rec_texts', []), data.get('rec_scores', [])):
                    if float(score) < max(.75, self.s.min_confidence) or not is_meaningful(str(text), 'en'):
                        continue
                    a, b, c, d = self._clamp(*rect, x2 - x1, y2 - y1)
                    if min(c - a, d - b) < self.s.min_box_size:
                        continue
                    new = Box(x1 + a, y1 + b, x1 + c, y1 + d, str(text), float(score))
                    if bubble_id(new, [balloon], .75) is None:
                        continue
                    overlaps = [old for old in boxes if
                                max(0, min(new.x2, old.x2) - max(new.x1, old.x1)) *
                                max(0, min(new.y2, old.y2) - max(new.y1, old.y1)) > .4 * min(new.w * new.h, old.w * old.h)]
                    if not overlaps and new.conf < max(.85, self.s.min_confidence):
                        continue
                    if any(old.conf >= .85 or old.conf >= new.conf
                           or (new.conf < .85 and (old.conf >= .65 or new.conf < old.conf + .10))
                           for old in overlaps):
                        continue
                    for old in overlaps:
                        boxes.remove(old)
                    boxes.append(new)
                    self.last_english_recovered_count += 1
            except Exception as exc:
                print(f'[ocr] İngilizce balon yeniden okuması atlandı: {exc}')

    def _retry_paddle_regions(self, rgb: np.ndarray, boxes: list[Box],
                              weak_boxes: list[Box]) -> None:
        """Düşük güvenli CJK bölgelerini komşu sütunlarıyla yeniden oku.

        Tam sayfada kaçan kalın/dikey yazı, yerel kırpımda doğru tespit
        edilebiliyor. Ek geçiş yalnızca açık zeminli küçük bölgelere uygulanır;
        düşük güvenli ikinci sonuçlar kabul edilmez.
        """
        H, W = rgb.shape[:2]
        tried: list[tuple[int, int, int, int]] = []

        def cjk_count(text: str) -> int:
            return sum("\u3400" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff"
                       for c in text)

        for weak in sorted(weak_boxes, key=lambda b: b.conf):
            if cjk_count(weak.text) == 0:
                continue
            if any(x1 <= weak.cx <= x2 and y1 <= weak.cy <= y2
                   for x1, y1, x2, y2 in tried):
                continue
            # Geniş kenar payı, eksik tespit edilmiş komşu dikey sütunu da alır.
            pad = max(20, min(120, int(max(weak.w, weak.h) * 0.8)))
            x1, y1, x2, y2 = self._clamp(
                weak.x1 - pad, weak.y1 - pad, weak.x2 + pad, weak.y2 + pad, W, H
            )
            if (x2 - x1) * (y2 - y1) > W * H * 0.20:
                continue
            crop = np.ascontiguousarray(rgb[y1:y2, x1:x2])
            if float(np.mean(np.min(crop, axis=2) > 205)) < 0.70:
                continue
            tried.append((x1, y1, x2, y2))
            try:
                result = self._predict(crop)
                data = getattr(result, "json", result)
                if isinstance(data, str):
                    data = json.loads(data)
                data = data.get("res", data) if isinstance(data, dict) else {}
                candidates: list[Box] = []
                for rect, text, score in zip(data.get("rec_boxes", []),
                                             data.get("rec_texts", []),
                                             data.get("rec_scores", [])):
                    if float(score) < max(0.85, self.s.min_confidence) or cjk_count(str(text)) < 2:
                        continue
                    a, b, c, d = self._clamp(*rect, x2 - x1, y2 - y1)
                    if min(c - a, d - b) < self.s.min_box_size:
                        continue
                    candidates.append(Box(x1 + a, y1 + b, x1 + c, y1 + d,
                                          text=str(text), conf=float(score)))
                # Yeni okuma, başlangıçtaki sorunlu bölgeyi gerçekten içermeli.
                if not any(b.x1 <= weak.cx <= b.x2 and b.y1 <= weak.cy <= b.y2
                           for b in candidates):
                    continue
                for new in candidates:
                    overlaps = []
                    for old in boxes:
                        intersection = max(0, min(new.x2, old.x2) - max(new.x1, old.x1)) * max(
                            0, min(new.y2, old.y2) - max(new.y1, old.y1))
                        if intersection > 0.5 * min(new.w * new.h, old.w * old.h):
                            overlaps.append(old)
                    if any(old.conf >= new.conf for old in overlaps):
                        continue
                    for old in overlaps:
                        boxes.remove(old)
                    boxes.append(new)
            except Exception as e:
                print(f"[ocr] Bölgesel yeniden okuma atlandı: {e}")

    # ------------------------------------------------------------------
    @staticmethod
    def _clamp(x1, y1, x2, y2, w, h):
        return max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))

    @staticmethod
    def _is_cut(y1: int, y2: int, H: int, edge: int) -> bool:
        return y1 <= edge or y2 >= H - edge

    # ------------------------------------------------------------------
    # manga-ocr: toplu (batch) + GPU'da fp16
    # ------------------------------------------------------------------
    def _manga_batch(self, crops: list[Image.Image]) -> list[str]:
        if not crops:
            return []
        texts = []
        batch_n = max(1, min(4, int(self.s.manga_batch)))
        for i in range(0, len(crops), batch_n):
            batch=crops[i:i+batch_n]
            budget=getattr(self,'_prediction_budget',None)
            if budget is None:
                budget=self._prediction_budget=PredictionBudget()
            key=tuple(budget.key(np.asarray(crop)) for crop in batch)
            try:
                texts.extend(budget.call('manga',key,lambda:self.manga.recognize(batch),['']*len(batch)))
            finally:
                self.last_predict_count=budget.used
                self.has_pending_retries=bool(budget.pending)
                self.pending_retry_count=len(budget.pending)
        return texts

    # ------------------------------------------------------------------
    # Yoğun metin bölme: sütun/satır projeksiyonu
    # ------------------------------------------------------------------
    @staticmethod
    def _ink_mask(gray: np.ndarray) -> np.ndarray:
        import cv2
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        ink = th == 0                     # koyu pikseller
        if ink.mean() > 0.5:              # mürekkep azınlıktadır; koyu zemin + açık yazı
            ink = ~ink
        return ink

    @staticmethod
    def _runs(profile: np.ndarray, min_val: float) -> list[list[int]]:
        on = profile > min_val
        runs, start = [], None
        for i, v in enumerate(on):
            if v and start is None:
                start = i
            elif not v and start is not None:
                runs.append([start, i])
                start = None
        if start is not None:
            runs.append([start, len(on)])
        return runs

    @staticmethod
    def _clean_lines(runs: list[list[int]]) -> list[list[int]]:
        merged: list[list[int]] = []
        for r in runs:
            if merged and r[0] - merged[-1][1] <= 1:
                merged[-1][1] = r[1]
            else:
                merged.append(list(r))
        if len(merged) < 2:
            return merged
        widths = sorted(b - a for a, b in merged)
        med = widths[len(widths) // 2]
        # furigana / gürültü gibi çok ince satırları at
        return [r for r in merged if (r[1] - r[0]) >= med * 0.45]

    @staticmethod
    def _split_along(along: np.ndarray, s: int, e: int, max_len: int, search: int) -> list[tuple[int, int]]:
        segs, cur = [], s
        max_len = max(8, max_len)
        while e - cur > max_len * 1.25:
            target = cur + max_len
            lo = max(cur + max_len // 2, target - max(2, search))
            hi = min(e - 1, target)
            cut = lo + int(np.argmin(along[lo:hi + 1])) if hi > lo else target
            segs.append((cur, cut))
            cur = cut
        segs.append((cur, e))
        return segs

    def _segment_region(self, rgb, gray, x1, y1, x2, y2, vertical) -> list[Image.Image]:
        H, W = rgb.shape[:2]
        cx1, cy1, cx2, cy2 = self._clamp(x1 - 4, y1 - 4, x2 + 4, y2 + 4, W, H)
        whole = [Image.fromarray(np.ascontiguousarray(rgb[cy1:cy2, cx1:cx2]))]
        if not self.s.ja_dense_split:
            return whole
        g = gray[cy1:cy2, cx1:cx2]
        if min(g.shape) < 12:
            return whole

        ink = self._ink_mask(g)
        prof = ink.sum(axis=0) if vertical else ink.sum(axis=1)
        across_len = g.shape[0] if vertical else g.shape[1]
        lines = self._clean_lines(self._runs(prof, max(1.0, across_len * 0.01)))
        if not lines:
            return whole
        thick = sorted(b - a for a, b in lines)
        cs = max(4, thick[len(thick) // 2])          # yaklaşık karakter boyu
        if max(g.shape) / cs <= self.s.ja_dense_ratio:
            return whole                             # normal balon -> tek parça daha iyi

        if vertical:
            lines.sort(key=lambda r: -r[0])          # sağdan sola sütunlar
        else:
            lines.sort(key=lambda r: r[0])           # yukarıdan aşağı satırlar

        gh, gw = g.shape
        crops: list[Image.Image] = []
        for a, b in lines:
            sub = ink[:, a:b] if vertical else ink[a:b, :]
            along = sub.sum(axis=1) if vertical else sub.sum(axis=0)
            nz = np.nonzero(along)[0]
            if nz.size == 0:
                continue
            s, e = int(nz[0]), int(nz[-1]) + 1
            for p, q in self._split_along(along, s, e, int(cs * self.s.ja_seg_chars), int(cs)):
                if vertical:
                    X1, X2, Y1, Y2 = a - 3, b + 3, p - 3, q + 3
                else:
                    X1, X2, Y1, Y2 = p - 3, q + 3, a - 3, b + 3
                X1, Y1 = max(0, X1), max(0, Y1)
                X2, Y2 = min(gw, X2), min(gh, Y2)
                if X2 - X1 < 4 or Y2 - Y1 < 4:
                    continue
                crops.append(Image.fromarray(np.ascontiguousarray(
                    rgb[cy1 + Y1:cy1 + Y2, cx1 + X1:cx1 + X2])))
        return crops or whole

    # ------------------------------------------------------------------
    def _iter_paddle_manga(self, rgb: np.ndarray, edge: int, panels,
                           viewport_edges=frozenset(('top', 'bottom', 'left', 'right')),
                           bubbles=None
                           ) -> Iterator[list[OCRBlock]]:
        import cv2
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        blocks = self._process_paddle(rgb, edge, panels, viewport_edges,
                                      finish_budget=False, bubbles=bubbles)
        for panel_batch in self._panel_batches(blocks, panels):
            for i in range(0, len(panel_batch), 3):
                chunk = panel_batch[i:i+3]
                all_crops: list[Image.Image] = []
                spans: list[tuple[int, int]] = []
                complete = [b for b in chunk if not b.cut]
                for b in complete:
                    crops = self._segment_region(rgb, gray, b.x1, b.y1, b.x2, b.y2, b.vertical)
                    spans.append((len(all_crops), len(all_crops) + len(crops)))
                    all_crops.extend(crops)
                try:
                    texts = self._manga_batch(all_crops)
                    for b, (s, e) in zip(complete, spans):
                        if any(not value for value in texts[s:e]):
                            continue
                        text = clean_text(''.join(texts[s:e]), self.lang)
                        if is_meaningful(text, self.lang):
                            b.text = text
                except Exception as e:
                    # Preserve Paddle results on a recognizer failure. Cut markers
                    # must still reach the scroll cache even if the helper dies.
                    print(f'[ocr] manga-ocr yeniden okuması atlandı; Paddle korunuyor: {e}')
                yield chunk
        budget=getattr(self,'_prediction_budget',None)
        if budget is not None:
            budget.finish()
