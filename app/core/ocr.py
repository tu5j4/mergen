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
from .bubbles import bubble_id, detect_bubbles, open_white_edge
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
def _sentence_case(text: str) -> str:
    t = text.lower()
    t = re.sub(r"(^|[.!?…]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    t = re.sub(r"\bi\b", "I", t)
    t = re.sub(r"\bi'(m|ll|ve|d)\b", lambda m: "I'" + m.group(1), t)
    return t


def clean_text(text: str, lang: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip()
    if lang in ("ja", "zh", "zh_tw"):
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[.・]{2,}", "…", text)
    else:
        text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
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
        want_paddle = lang in LANGS
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
                paddle_models = (
                    {"text_detection_model_name": "PP-OCRv5_mobile_det",
                     "text_recognition_model_name": "PP-OCRv5_mobile_rec"}
                    if settings.paddle_mobile else {}
                )
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
            device = 'cpu' if settings.use_gpu == 'no' else settings.manga_device
            try:
                self.manga = MangaClient(device)
            except Exception as exc:
                self.manga_warning = str(exc)
                if device == 'auto':
                    try:
                        self.manga = MangaClient('cpu')
                        self.manga_warning = f'GPU başlatılamadı; manga-ocr CPU: {exc}'
                    except Exception:
                        pass
                print(f'[ocr] Manga yardımcı işlem: {self.manga_warning}')
            self.gpu = self.manga is not None and self.manga.device == 'cuda'

    def close(self):
        if self.manga is not None:
            self.manga.close()
            self.manga = None
        self.paddle = None

    # ------------------------------------------------------------------
    def process_iter(self, rgb: np.ndarray, edge_px: int = 3,
                     viewport_edges: frozenset[str] = frozenset(('top', 'bottom', 'left', 'right'))
                     ) -> Iterator[list[OCRBlock]]:
        panels = detect_panels(rgb)
        if self.manga is not None:
            yield from self._iter_paddle_manga(rgb, edge_px, panels, viewport_edges)
        elif self.paddle is not None:
            blocks = self._process_paddle(rgb, edge_px, panels, viewport_edges)
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
            for old in unique:
                overlap = max(0, min(b.x2, old.x2)-max(b.x1, old.x1)) * max(0, min(b.y2, old.y2)-max(b.y1, old.y1))
                if clean_text(b.text, self.lang) == clean_text(old.text, self.lang) and overlap > .45 * min(b.w*b.h, old.w*old.h):
                    duplicate = True
                    break
            if not duplicate:
                unique.append(b)
        ids = [bubble_id(b, bubbles, .75 if self.lang == 'ja' else 0.0)
               for b in unique] if bubbles else None
        pids = [panel_id(b, panels) for b in unique] if panels else None
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
        for member in members:
            bid = bubble_id(member, bubbles, min_coverage)
            if bid is None:
                continue
            b = bubbles[bid]
            area = (b.x2-b.x1)*(b.y2-b.y1)
            if area > W*H*.18 or area > max(1, (x2-x1)*(y2-y1))*12:
                continue
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
                y1, y2 = min(y1, b.y1), max(y2, b.y2)
        if rgb is not None:
            group = Box(x1, y1, x2, y2)
            for side in viewport_edges:
                if side not in edges and open_white_edge(rgb, group, side):
                    edges.add(side)
        return bool(edges), 'top' in edges, y1, y2, frozenset(edges)

    def process(self, rgb: np.ndarray) -> list[OCRBlock]:
        return [b for batch in self.process_iter(rgb) for b in batch]

    def _process_paddle(self, rgb: np.ndarray, edge: int, panels=None,
                        viewport_edges=frozenset(('top', 'bottom', 'left', 'right'))) -> list[OCRBlock]:
        """PP-OCR v3/v5 sonuçlarını sürümden bağımsız şekilde OCRBlock'a dönüştürür."""
        H, W = rgb.shape[:2]
        bubbles = detect_bubbles(rgb, self.s.bubble_min_area) if self.s.bubble_detection else []
        try:
            result = next(iter(self.paddle.predict(rgb)))
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
        panels = detect_panels(rgb) if panels is None else panels
        blocks: list[OCRBlock] = []
        for group in self._layout_groups(boxes, bubbles, panels):
            members = order_boxes(group, self.info["vertical_rtl"])
            x1, y1, x2, y2 = bbox_of(members)
            vertical = sum(b.vertical for b in members) > len(members) / 2
            cut, cut_top, y1, y2, cut_edges = self._cut_region(
                x1, y1, x2, y2, W, H, edge, members, bubbles,
                min_coverage=.75 if self.lang == 'ja' else 0.0,
                rgb=rgb, viewport_edges=viewport_edges)
            if cut:
                blocks.append(OCRBlock(x1, y1, x2, y2, "", vertical, cut=True,
                                       cut_top=cut_top, cut_edges=cut_edges))
                continue
            text = clean_text(self.info["joiner"].join(b.text for b in members), self.lang)
            if is_meaningful(text, self.lang):
                blocks.append(OCRBlock(x1, y1, x2, y2, text, vertical))
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
            if not candidates or retried >= 2:
                out.append((rect, text, score))
                continue
            bubble = min(candidates, key=lambda b: (b.x2 - b.x1) * (b.y2 - b.y1))
            regions = [(bubble.x1, bubble.y1, bubble.x2, bubble.y2),
                       (x1, y1, x2, min(y2, bubble.y1)),
                       (x1, max(y1, bubble.y2), x2, y2),
                       (x1, max(y1, bubble.y1), min(x2, bubble.x1), min(y2, bubble.y2)),
                       (max(x1, bubble.x2), max(y1, bubble.y1), x2, min(y2, bubble.y2))]
            recovered = []
            inside_found = False
            retried += 1
            try:
                for index, (a, b, c, d) in enumerate(regions):
                    a, b, c, d = self._clamp(a, b, c, d, W, H)
                    if min(c - a, d - b) < 20:
                        continue
                    result = next(iter(self.paddle.predict(np.ascontiguousarray(rgb[b:d, a:c]))))
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
            out.extend(recovered if inside_found else [(rect, text, score)])
        return {"rec_boxes": [r for r, t, s in out], "rec_texts": [t for r, t, s in out],
                "rec_scores": [s for r, t, s in out]}

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
            if len(tried) >= 4:
                break
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
                result = next(iter(self.paddle.predict(crop)))
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
            texts.extend(self.manga.recognize(crops[i:i+batch_n]))
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
                           viewport_edges=frozenset(('top', 'bottom', 'left', 'right'))
                           ) -> Iterator[list[OCRBlock]]:
        import cv2
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        blocks = self._process_paddle(rgb, edge, panels, viewport_edges)
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
                        text = clean_text(''.join(texts[s:e]), self.lang)
                        if is_meaningful(text, self.lang):
                            b.text = text
                except Exception as e:
                    # Preserve Paddle results on a recognizer failure. Cut markers
                    # must still reach the scroll cache even if the helper dies.
                    print(f'[ocr] manga-ocr yeniden okuması atlandı; Paddle korunuyor: {e}')
                yield chunk
