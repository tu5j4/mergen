"""Conservative, CPU-only page layout; no additional OCR/model passes.

Unknown layouts remain one region. Panel IDs are local to this capture, not
stable page identities (scroll caching continues to use content coordinates).
"""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Panel:
    x1: int
    y1: int
    x2: int
    y2: int


def detect_panels(rgb: np.ndarray) -> list[Panel]:
    h, w = rgb.shape[:2]
    if not h or not w:
        return []
    scale = min(1.0, 1000 / max(h, w))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ink = gray < 225
    hh, ww = gray.shape
    leaves = []

    def split(x1, y1, x2, y2, depth=0):
        region = ink[y1:y2, x1:x2]
        candidates = []
        for axis, length in (() if min(region.shape) < 100 else ((0, y2-y1), (1, x2-x1))):
            # Only near-empty gutters spanning the entire current region.
            profile = region.mean(axis=1 if axis == 0 else 0)
            # A narrow publisher/sidebar strip must not hide an otherwise
            # empty gutter. Large cross-panel captions still block splitting.
            empty = profile < 0.05
            edges = np.diff(np.r_[False, empty, False].astype(np.int8))
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
                if b-a < max(5, int(8*scale)) or a < max(45, length*.12) or length-b < max(45, length*.12):
                    continue
                band = region[a:b] if axis == 0 else region[:, a:b]
                persistent = np.flatnonzero(band.mean(axis=0 if axis == 0 else 1) > .8)
                across = region.shape[1 if axis == 0 else 0]
                offset = x1 if axis == 0 else y1
                full = ww if axis == 0 else hh
                persistent = persistent[(persistent+offset > full*.02) & (persistent+offset < full*.98)]
                # Empty scenery inside a panel still has its two frame edges.
                # A true gutter has no such widely separated crossing borders.
                if len(persistent) > 1 and persistent[-1]-persistent[0] > across*.4:
                    continue
                before = region[:a] if axis == 0 else region[:, :a]
                after = region[b:] if axis == 0 else region[:, b:]
                if before.mean() > .025 and after.mean() > .025:
                    candidates.append((b-a, axis, int(a), int(b)))
        if not candidates or depth >= 8:
            leaves.append((x1, y1, x2, y2))
            return
        _, axis, a, b = max(candidates)
        if axis == 0:
            split(x1, y1, x2, y1+a, depth+1)
            split(x1, y1+b, x2, y2, depth+1)
        else:
            split(x1, y1, x1+a, y2, depth+1)
            split(x1+b, y1, x2, y2, depth+1)

    split(0, 0, ww, hh)
    return [Panel(round(a/scale), round(b/scale), min(w, round(c/scale)), min(h, round(d/scale)))
            for a, b, c, d in leaves]


def panel_id(box, panels: list[Panel]) -> int | None:
    # A box straddling a gutter is deliberately unassigned; do not invent a
    # split for a sound effect/title spanning panels.
    matches = []
    area = max(1, (box.x2-box.x1)*(box.y2-box.y1))
    for i, p in enumerate(panels):
        overlap = max(0, min(box.x2, p.x2)-max(box.x1, p.x1)) * max(0, min(box.y2, p.y2)-max(box.y1, p.y1))
        if overlap / area >= .85:
            matches.append((overlap, i))
    return max(matches)[1] if matches else None


def reading_order(items, rtl=False):
    """Recursive XY order: full-width row breaks first, then column breaks."""
    items = list(items)
    if len(items) < 2:
        return items
    for axis in ('y', 'x'):
        start, end = axis+'1', axis+'2'
        ordered = sorted(items, key=lambda b: getattr(b, start))
        boundary = getattr(ordered[0], end)
        for i in range(1, len(ordered)):
            if getattr(ordered[i], start) >= boundary + 3:
                first, second = ordered[:i], ordered[i:]
                if axis == 'x' and rtl:
                    first, second = second, first
                return reading_order(first, rtl) + reading_order(second, rtl)
            boundary = max(boundary, getattr(ordered[i], end))
    return sorted(items, key=lambda b: (b.y1, -b.x2 if rtl else b.x1))


def order_by_panel(blocks, panels, rtl=False):
    blocks = list(blocks)
    groups = {}
    for index, b in enumerate(blocks):
        pid = panel_id(b, panels)
        # Unknown/spanning captions belong at their visual position, not
        # automatically after every identified panel on the page.
        groups.setdefault(('panel', pid) if pid is not None else ('unknown', index), []).append(b)

    @dataclass
    class Region:
        x1: int
        y1: int
        x2: int
        y2: int
        members: list

    regions = [Region(min(b.x1 for b in group), min(b.y1 for b in group),
                      max(b.x2 for b in group), max(b.y2 for b in group), group)
               for group in groups.values()]
    return [b for region in reading_order(regions, rtl)
            for b in reading_order(region.members, rtl)]
