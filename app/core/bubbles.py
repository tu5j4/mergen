"""Hafif, model gerektirmeyen konuşma balonu aday tespiti.

Bu modül metni tekrar okumaz; OCR kutularının hangi balona ait olduğunu ayırır.
Bu nedenle yakın iki balonun tek çeviri kutusunda birleşmesini engeller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import cv2
import numpy as np


@dataclass(frozen=True)
class Bubble:
    x1: int
    y1: int
    x2: int
    y2: int
    contour: np.ndarray | None = field(default=None, compare=False, repr=False)

    def contains(self, x: float, y: float) -> bool:
        if not (self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2):
            return False
        return self.contour is None or cv2.pointPolygonTest(self.contour, (float(x), float(y)), False) >= 0


def detect_bubbles(rgb: np.ndarray, min_area: int = 900) -> list[Bubble]:
    """Açık renkli, kapalı konuşma balonlarını bulur.

    Koyu/çerçevesiz balonlar için boş sonuç vermek normaldir; çağıran kod o durumda
    eski, hizalama tabanlı gruplamaya güvenmeye devam eder.
    """
    if rgb.size == 0:
        return []
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Beyaz zemini genişletmek ince balon çizgisini siliyordu. Siyah çizgideki
    # küçük boşlukları kapat; balon içini dışarıdan ayıran sınırı koru.
    ink = (gray < 205).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    mask = (1 - ink) * 255
    # Panel sınırının içindeki beyaz balonlar da ayrı bileşenlerdir;
    # RETR_EXTERNAL bunları dış arka planın altında gizliyordu.
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    result: list[Bubble] = []
    for index, contour in enumerate(contours):
        if hierarchy[0][index][3] != -1:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if bw < 28 or bh < 20 or area < min_area:
            continue
        # Tüm sayfayı/paneli kaplayan düz arka planı balon diye alma.
        if bw * bh > w * h * 0.70 or area / max(1, bw * bh) < 0.22:
            continue
        result.append(Bubble(x, y, x + bw, y + bh, contour))
    return result


def bubble_id(box, bubbles: list[Bubble], min_coverage: float = 0.0) -> int | None:
    """Kutunun merkezini içeren en küçük balonu döndürür."""
    def covers(b):
        if not b.contains(box.cx, box.cy):
            return False
        if not min_coverage:
            return True
        area = max(1, (box.x2-box.x1)*(box.y2-box.y1))
        overlap = max(0, min(box.x2, b.x2)-max(box.x1, b.x1)) * max(0, min(box.y2, b.y2)-max(box.y1, b.y1))
        if overlap / area < min_coverage:
            return False
        # Bounding rectangles alone can encompass scenery outside irregular
        # contours. Sample the interior, allowing a little OCR padding.
        return sum(b.contains(box.x1 + (box.x2-box.x1)*x,
                              box.y1 + (box.y2-box.y1)*y)
                   for x in (.2, .5, .8) for y in (.1, .3, .5, .7, .9)) / 15 >= min_coverage

    candidates = [(i, (b.x2 - b.x1) * (b.y2 - b.y1))
                  for i, b in enumerate(bubbles) if covers(b)]
    return min(candidates, key=lambda item: item[1])[0] if candidates else None


def open_white_edge(rgb: np.ndarray, box, side: str) -> bool:
    """Find a compact light balloon interior continuing beyond a viewport edge.

    This is a conservative fallback for open outlines that the contour detector
    cannot close. A plain white page, or a broad white panel, is rejected.
    """
    h, w = rgb.shape[:2]
    if min(h, w) < 32:
        return False
    if side in ('top', 'bottom'):
        distance = box.y1 if side == 'top' else h - box.y2
        if distance > min(90, max(30, int(box.h * 1.5))):
            return False
        band = rgb[:6] if side == 'top' else rgb[-6:]
        profile = np.mean(band, axis=(0, 2))
        inward = rgb[12:18] if side == 'top' else rgb[-18:-12]
        inner_profile = np.mean(inward, axis=(0, 2))
        center, text_span, length = int(box.cx), box.w, w
    else:
        distance = box.x1 if side == 'left' else w - box.x2
        if distance > min(90, max(30, int(box.w * 1.5))):
            return False
        band = rgb[:, :6] if side == 'left' else rgb[:, -6:]
        profile = np.mean(band, axis=(1, 2))
        inward = rgb[:, 12:18] if side == 'left' else rgb[:, -18:-12]
        inner_profile = np.mean(inward, axis=(1, 2))
        center, text_span, length = int(box.cy), box.h, h
    if center < 1 or center >= length - 1 or profile[center] < 215:
        return False
    light = profile >= 215
    left = center
    right = center
    while left > 0 and light[left - 1]:
        left -= 1
    while right < length - 1 and light[right + 1]:
        right += 1
    width = right - left + 1
    if width < max(12, text_span * 0.8) or width > length * 0.45:
        return False
    # Straight panel edges also frame a white interval; an oval speech balloon
    # changes width as its curved outline moves inward from the screen edge.
    if inner_profile[center] < 215:
        return False
    inner_light = inner_profile >= 215
    inner_left = center
    inner_right = center
    while inner_left > 0 and inner_light[inner_left - 1]:
        inner_left -= 1
    while inner_right < length - 1 and inner_light[inner_right + 1]:
        inner_right += 1
    if abs((inner_right - inner_left + 1) - width) < max(4, width * 0.03):
        return False
    flank = max(12, min(60, text_span))
    before = profile[max(0, left - flank):left]
    after = profile[right + 1:min(length, right + flank + 1)]
    return bool(before.size and after.size and
                np.min(before) < 150 and np.min(after) < 150)
