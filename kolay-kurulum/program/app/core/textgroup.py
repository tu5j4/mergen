"""
OCR kutularını konuşma balonu / paragraf bazında gruplama ve okuma sırasına dizme.
Saf Python -> mobil porta birebir taşınabilir algoritma.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Box:
    x1: int
    y1: int
    x2: int
    y2: int
    text: str = ""
    conf: float = 1.0

    @property
    def w(self) -> int:
        return max(1, self.x2 - self.x1)

    @property
    def h(self) -> int:
        return max(1, self.y2 - self.y1)

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def vertical(self) -> bool:
        return self.h > self.w * 1.5

    @property
    def char_size(self) -> int:
        # Yatay satırda karakter boyu ~ yükseklik, dikey sütunda ~ genişlik
        return min(self.w, self.h)


def _ov(a1: int, a2: int, b1: int, b2: int) -> int:
    return max(0, min(a2, b2) - max(a1, b1))


def group_boxes(boxes: list[Box], gap_ratio: float = 0.65,
                bubble_ids: list[int | None] | None = None,
                panel_ids: list[int | None] | None = None,
                same_bubble_gap_ratio: float | None = None,
                allow_short_bubble_columns: bool = False) -> list[list[int]]:
    """
    Birbirine yakın, HİZALI ve benzer puntodaki kutuları union-find ile birleştirir.
    Hizalılık şartı (yan yana -> dikeyde örtüşme / alt alta -> yatayda örtüşme)
    yoğun sayfalarda çapraz komşu balonların birbirine karışmasını engeller.
    """
    n = len(boxes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        a = boxes[i]
        for j in range(i + 1, n):
            b = boxes[j]
            if panel_ids is not None and panel_ids[i] != panel_ids[j]:
                continue
            # Farklı balonları ve balon dışındaki efekt/dipnot yazılarını ayır.
            # İkisi de balon dışında kaldıysa hizalama tabanlı gruplama sürer.
            if bubble_ids is not None and bubble_ids[i] != bubble_ids[j]:
                continue
            # Yatay dipnotlar, yakındaki dikey konuşma sütunlarına zincirleme
            # bağlanmamalı. Kare/tek karakter kutularında yönü kesin sayma.
            a_horizontal = a.w > a.h * 1.5
            b_horizontal = b.w > b.h * 1.5
            if (a.vertical and b_horizontal) or (b.vertical and a_horizontal):
                continue
            ca, cb = a.char_size, b.char_size
            if max(ca, cb) / max(1, min(ca, cb)) > 2.2:
                continue
            # Sayfa kenarındaki uzun dikey telif/not satırını, yakınındaki balon
            # sütunlarına bağlama. Bu iki yapı benzer genişlikte olsa da yükseklikleri
            # belirgin biçimde farklıdır.
            # Japanese may waive only this height guard inside one verified
            # balloon. Font size, direction, alignment, gap and panel guards stay.
            known_same_bubble = (bubble_ids is not None and bubble_ids[i] is not None
                                 and bubble_ids[i] == bubble_ids[j])
            if (a.vertical and b.vertical
                    and max(a.h, b.h) / max(1, min(a.h, b.h)) > 2.7
                    and not (allow_short_bubble_columns and known_same_bubble)):
                continue
            gap = max(ca, cb) * gap_ratio
            hgap = max(0, max(a.x1, b.x1) - min(a.x2, b.x2))
            vgap = max(0, max(a.y1, b.y1) - min(a.y2, b.y2))
            xo = _ov(a.x1, a.x2, b.x1, b.x2) / max(1, min(a.w, b.w))
            yo = _ov(a.y1, a.y2, b.y1, b.y2) / max(1, min(a.h, b.h))
            # Korean webtoon paragraphs can have unusually generous leading.
            # Relax only stacked, aligned horizontal lines in the SAME known
            # balloon; unknown regions and neighboring balloons stay unchanged.
            if (same_bubble_gap_ratio is not None and bubble_ids is not None
                    and bubble_ids[i] is not None and a_horizontal and b_horizontal
                    and xo > 0.65 and vgap <= max(ca, cb) * same_bubble_gap_ratio):
                union(i, j)
            # Ayrı balonların uçları hafifçe örtüşebilir; bu, aynı dikey
            # paragrafta oldukları anlamına gelmez (örn. uzun SASUKE sütunu).
            side_overlap = 0.6 if a.vertical and b.vertical else 0.3
            if (yo > side_overlap and hgap <= gap) or (xo > 0.3 and vgap <= gap):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def order_boxes(boxes: list[Box], allow_vertical_rtl: bool) -> list[Box]:
    """Okuma sırası: dikey metin -> sütunlar sağdan sola; yatay -> satırlar yukarıdan aşağı."""
    if not boxes:
        return []
    vertical_count = sum(1 for b in boxes if b.vertical)
    if allow_vertical_rtl and vertical_count > len(boxes) / 2:
        avg_w = sum(b.w for b in boxes) / len(boxes)
        cols: list[list[Box]] = []
        for b in sorted(boxes, key=lambda b: -b.cx):
            if cols and abs(cols[-1][0].cx - b.cx) < avg_w * 0.5:
                cols[-1].append(b)
            else:
                cols.append([b])
        return [b for col in cols for b in sorted(col, key=lambda b: b.y1)]

    avg_h = sum(b.h for b in boxes) / len(boxes)
    rows: list[list[Box]] = []
    for b in sorted(boxes, key=lambda b: b.cy):
        if rows and abs(rows[-1][0].cy - b.cy) < avg_h * 0.5:
            rows[-1].append(b)
        else:
            rows.append([b])
    return [b for row in rows for b in sorted(row, key=lambda b: b.x1)]


def bbox_of(boxes: list[Box]) -> tuple[int, int, int, int]:
    return (min(b.x1 for b in boxes), min(b.y1 for b in boxes),
            max(b.x2 for b in boxes), max(b.y2 for b in boxes))
