"""
Şeffaf, her zaman üstte, tıklamaları alttaki pencereye geçiren çeviri katmanı.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, Slot
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..config import Settings
from ..platform_utils import exclude_from_capture

_TEXT_FLAGS = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)


class OverlayWindow(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.s = settings
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowTitle("mergen · çeviri katmanı")

        self._blocks: list[dict] = []
        self._layout: list[tuple[QRectF, str, QFont, QColor, QColor]] = []
        self._font_cache: dict = {}
        self._excluded = False
        self._platform_done = False
        self._show_region_border = False

    # ------------------------------------------------------------------
    def ensure_platform_setup(self) -> None:
        if not self._platform_done:
            self._excluded = exclude_from_capture(self)
            self._platform_done = True
            print(f"[overlay] ekran yakalamadan hariç: {self._excluded}")

    def is_capture_excluded(self) -> bool:
        return self._excluded

    def set_region(self, rect: QRect) -> None:
        self.setGeometry(rect)
        self.clear_blocks()

    def flash_border(self, on: bool) -> None:
        self._show_region_border = on
        self.update()

    # ------------------------------------------------------------------
    @Slot(list)
    def set_blocks(self, blocks: list[dict]) -> None:
        self._blocks = blocks
        self._relayout()
        self.update()

    @Slot()
    def clear_blocks(self) -> None:
        self._blocks = []
        self._layout = []
        self.update()

    def refresh_style(self) -> None:
        self._font_cache.clear()
        self._relayout()
        self.update()

    # ------------------------------------------------------------------
    def _make_font(self, px: int) -> QFont:
        f = QFont(self.s.font_family)
        f.setPixelSize(px)
        f.setBold(self.s.font_bold)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return f

    def _fit_font(self, text: str, rect: QRectF, compact: bool = False) -> QFont:
        lo = self.s.min_font_px
        hi = max(lo, min(22, int(self.s.max_font_px * 0.70))) if compact else self.s.max_font_px
        w, h = int(rect.width()), int(rect.height())
        best = lo
        while lo <= hi:
            mid = (lo + hi) // 2
            fm = QFontMetrics(self._make_font(mid))
            br = fm.boundingRect(QRect(0, 0, w, 100000), _TEXT_FLAGS, text)
            # en uzun kelime de sığmalı
            longest = max((fm.horizontalAdvance(word) for word in text.split()), default=0)
            if br.height() <= h and br.width() <= w and longest <= w:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return self._make_font(best)

    def _cached_font(self, text: str, rect: QRectF, compact: bool = False) -> QFont:
        key = (text, int(rect.width()), int(rect.height()), compact)
        f = self._font_cache.get(key)
        if f is None:
            if len(self._font_cache) > 800:
                self._font_cache.clear()
            f = self._fit_font(text, rect, compact)
            self._font_cache[key] = f
        return f

    def _relayout(self) -> None:
        self._layout = []
        W, H = self.width(), self.height()
        pad = self.s.box_padding
        alpha = int(255 * max(0.0, min(1.0, self.s.overlay_opacity)))
        for index, b in enumerate(self._blocks):
            x, y, w, h = b["x"], b["y"], b["w"], b["h"]
            # Dikey (Japonca) sütunlar dar olur; Türkçe yatay yazı için kutuyu genişlet
            compact = bool(b.get("vertical") or h > w * 1.3)
            if compact:
                # Genişleyen Türkçe kutusunun komşu balonlara taşmasına izin verme.
                left_gap = right_gap = float("inf")
                for other_index, other in enumerate(self._blocks):
                    if other_index == index:
                        continue
                    oy, oh = other["y"], other["h"]
                    if min(y + h, oy + oh) - max(y, oy) <= min(h, oh) * 0.25:
                        continue
                    ox, ow = other["x"], other["w"]
                    if ox + ow <= x:
                        left_gap = min(left_gap, x - (ox + ow))
                    elif ox >= x + w:
                        right_gap = min(right_gap, ox - (x + w))
                safe_w = w + 2 * max(0.0, min(left_gap, right_gap) - pad * 2)
                new_w = min(max(w, h * 0.55), w * 1.8, safe_w)
                x -= (new_w - w) / 2
                w = new_w
            rect = QRectF(x - pad, y - pad, w + 2 * pad, h + 2 * pad)
            # yatayda pencere içinde tut; dikeyde kenardan taşabilir (kaydırma sırasında)
            if rect.left() < 0:
                rect.moveLeft(0)
            if rect.right() > W:
                rect.moveRight(W)
            if compact and b.get('source_lang', self.s.source_lang) == 'ja':
                # Already-overlapping OCR columns have no positive "gap".
                # Reserve disjoint horizontal lanes, including padding, instead
                # of expanding both translated boxes into the same space.
                center = b['x'] + b['w'] / 2
                left, right = 0.0, float(W)
                for other_index, other in enumerate(self._blocks):
                    if other_index == index:
                        continue
                    if min(b['y'] + b['h'], other['y'] + other['h']) - max(b['y'], other['y']) <= min(b['h'], other['h']) * .25:
                        continue
                    other_center = other['x'] + other['w'] / 2
                    boundary = (center + other_center) / 2
                    if other_center < center:
                        left = max(left, boundary + 1)
                    elif other_center > center:
                        right = min(right, boundary - 1)
                rect.setLeft(max(rect.left(), left))
                rect.setRight(min(rect.right(), right))
            if rect.bottom() < 0 or rect.top() > H or rect.width() < 4 or rect.height() < 4:
                continue
            r, g, bl = b.get("bg", (255, 255, 255))
            lum = 0.299 * r + 0.587 * g + 0.114 * bl
            bg = QColor(r, g, bl, alpha)
            fg = QColor(15, 15, 15) if lum > 128 else QColor(245, 245, 245)
            inner = rect.adjusted(3, 2, -3, -2)
            font = self._cached_font(b["text"], inner, compact)
            self._layout.append((rect, b["text"], font, bg, fg))

    # ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        if self._show_region_border:
            p.setPen(QColor(0, 170, 255, 200))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        for rect, text, font, bg, fg in self._layout:
            path = QPainterPath()
            radius = min(10.0, rect.height() / 3, rect.width() / 3)
            path.addRoundedRect(rect, radius, radius)
            p.fillPath(path, bg)
            p.setFont(font)
            p.setPen(fg)
            p.drawText(rect.adjusted(3, 2, -3, -2), _TEXT_FLAGS, text)
        p.end()
