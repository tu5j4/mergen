"""
Şeffaf, her zaman üstte, tıklamaları alttaki pencereye geçiren çeviri katmanı.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer, Slot, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..config import Settings
from ..platform_utils import exclude_from_capture
from .overlay_layout import vertical_neighbors

_TEXT_FLAGS = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)


def surface_pieces(region: QRect, screens) -> list[tuple[object, QRect]]:
    """Split a logical region into one rectangle per intersecting screen."""
    if region.isNull() or region.width() <= 0 or region.height() <= 0:
        return []
    pieces = []
    for screen in screens:
        piece = screen.geometry().intersected(region)
        if piece.width() > 0 and piece.height() > 0:
            pieces.append((screen, piece))
    return pieces


class OverlayWindow(QWidget):
    capture_areas_changed = Signal(list)
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
        self._metrics_cache: dict = {}
        self._word_width_cache: dict = {}
        self._excluded = False
        self._platform_done = False
        self._show_region_border = False
        self._scroll_layout = None
        self._region_origin = QPoint(0, 0)
        self._region_size = QSize(0, 0)

    # ------------------------------------------------------------------
    def ensure_platform_setup(self) -> None:
        if not self._platform_done:
            if self.s.share_translations:
                exclude_from_capture(self, excluded=False)
                self._excluded = False
            else:
                self._excluded = exclude_from_capture(self)
            self._platform_done = True
            print(f"[overlay] ekran yakalamadan hariç: {self._excluded}")

    def is_capture_excluded(self) -> bool:
        return self._excluded

    def set_region(self, rect: QRect) -> None:
        self.setGeometry(rect)
        self._region_origin = QPoint(0, 0)
        self._region_size = QSize(rect.width(), rect.height())
        self.clear_blocks()

    def set_surface(self, rect: QRect, origin: QPoint, region_size: QSize) -> None:
        """Place this native surface inside the logical reading region.

        Blocks are laid out once in region-local coordinates; ``origin`` is the
        surface offset inside that region. Each surface therefore paints the
        same layout, clipped by its own native window, without a second reflow
        or a visible seam at mixed-DPI monitor boundaries.
        """
        self._region_origin = QPoint(origin)
        self._region_size = QSize(region_size)
        self.setGeometry(rect)
        self.clear_blocks()

    def _canvas_size(self) -> tuple[int, int]:
        size = self._region_size
        if size.width() <= 0 or size.height() <= 0:
            return self.width(), self.height()
        return size.width(), size.height()

    def flash_border(self, on: bool) -> None:
        self._show_region_border = on
        self.update()

    # ------------------------------------------------------------------
    @Slot(list)
    def set_blocks(self, blocks: list[dict]) -> None:
        if self._try_scroll_layout(blocks):
            self._blocks = blocks
            self.update()
            return
        self._blocks = blocks
        self._relayout()
        self.update()

    @Slot()
    def clear_blocks(self) -> None:
        self._blocks = []
        self._layout = []
        self._scroll_layout = None
        self.capture_areas_changed.emit([])
        self.update()

    def refresh_style(self) -> None:
        self._font_cache.clear()
        self._metrics_cache.clear()
        self._word_width_cache.clear()
        self._scroll_layout = None
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
            metric_key = (self.s.font_family, self.s.font_bold, mid)
            fm = self._metrics_cache.get(metric_key)
            if fm is None:
                fm = QFontMetrics(self._make_font(mid))
                self._metrics_cache[metric_key] = fm
            br = fm.boundingRect(QRect(0, 0, w, 100000), _TEXT_FLAGS, text)
            # en uzun kelime de sığmalı
            if len(self._word_width_cache) > 4096:
                self._word_width_cache.clear()
            widths = []
            for word in text.split():
                key = (*metric_key, word)
                width = self._word_width_cache.get(key)
                if width is None:
                    width = fm.horizontalAdvance(word)
                    self._word_width_cache[key] = width
                widths.append(width)
            longest = max(widths, default=0)
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

    def _layout_key(self, blocks):
        width, height = self._canvas_size()
        style = (width, height, self.s.box_padding, self.s.overlay_opacity,
                 self.s.font_family, self.s.font_bold, self.s.min_font_px,
                 self.s.max_font_px, self.s.source_lang)
        keys = [(b['y'], (b['x'], b['w'], b['h'], b['text'],
                         tuple(b.get('bg', (255, 255, 255))), bool(b.get('vertical')),
                         b.get('source_lang', self.s.source_lang))) for b in blocks]
        return style, keys

    def _try_scroll_layout(self, blocks) -> bool:
        cached = self._scroll_layout
        if not cached or not blocks or len(self._layout) != len(blocks):
            return False
        style, keys = self._layout_key(blocks)
        previous_style, previous = cached
        if style != previous_style or len(keys) != len(previous):
            return False
        dy = keys[0][0] - previous[0][0]
        if any(key != old_key or y - old_y != dy for (y, key), (old_y, old_key) in zip(keys, previous)):
            return False
        translated = [(rect.translated(0, dy), *rest) for rect, *rest in self._layout]
        _, region_h = self._canvas_size()
        if any(rect.bottom() < 0 or rect.top() > region_h for rect, *_ in translated):
            return False
        self._layout = translated
        self._scroll_layout = (style, keys)
        self._emit_areas()
        return True

    def capture_areas(self) -> list[tuple[float, float, float, float]]:
        ox, oy = self._region_origin.x(), self._region_origin.y()
        return [(r.x()+ox-2, r.y()+oy-2, r.width()+4, r.height()+4)
                for r, *_ in self._layout]

    def _emit_areas(self) -> None:
        self.capture_areas_changed.emit(self.capture_areas())

    def _relayout(self) -> None:
        self._layout = []
        W, H = self._canvas_size()
        surface_x, surface_y = self._region_origin.x(), self._region_origin.y()
        pad = self.s.box_padding
        alpha = int(255 * max(0.0, min(1.0, self.s.overlay_opacity)))
        neighbors = vertical_neighbors(self._blocks)
        for index, b in enumerate(self._blocks):
            x, y, w, h = b["x"], b["y"], b["w"], b["h"]
            # Dikey (Japonca) sütunlar dar olur; Türkçe yatay yazı için kutuyu genişlet
            compact = bool(b.get("vertical") or h > w * 1.3)
            if compact:
                # Genişleyen Türkçe kutusunun komşu balonlara taşmasına izin verme.
                left_gap = right_gap = float("inf")
                for other_index in neighbors[index]:
                    other = self._blocks[other_index]
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
                for other_index in neighbors[index]:
                    other = self._blocks[other_index]
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
            # Case is a display preference; preserve model/session/block text.
            display_text = b["text"]
            font = self._cached_font(display_text, inner, compact)
            self._layout.append((rect.translated(-surface_x, -surface_y), display_text, font, bg, fg))
        self._scroll_layout = self._layout_key(self._blocks)
        self._emit_areas()

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
            width, height = self._canvas_size()
            ox, oy = self._region_origin.x(), self._region_origin.y()
            if oy <= 0:
                p.drawLine(0, 0, self.width(), 0)
            if ox <= 0:
                p.drawLine(0, 0, 0, self.height())
            if oy + self.height() >= height:
                p.drawLine(0, self.height()-1, self.width(), self.height()-1)
            if ox + self.width() >= width:
                p.drawLine(self.width()-1, 0, self.width()-1, self.height())

        for rect, text, font, bg, fg in self._layout:
            path = QPainterPath()
            radius = min(10.0, rect.height() / 3, rect.width() / 3)
            path.addRoundedRect(rect, radius, radius)
            p.fillPath(path, bg)
            p.setFont(font)
            p.setPen(fg)
            p.drawText(rect.adjusted(3, 2, -3, -2), _TEXT_FLAGS, text)
        p.end()


class OverlayGroup(QObject):
    """One always-on-top native surface per monitor inside the reading region.

    A single top-level QWidget cannot span monitors with different device pixel
    ratios without one side being rendered at the wrong scale. This group lays
    out translations once in region-local logical coordinates and gives every
    screen an independent surface, its own DPI, and the correct native handle.
    """

    capture_areas_changed = Signal(list)
    surfaces_changed = Signal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.s = settings
        self._region = QRect()
        self._surfaces: list[OverlayWindow] = []
        self._visible = False
        self._areas: dict[OverlayWindow, list] = {}
        self._canvas = OverlayWindow(settings)
        self._rebuild_queued = False
        self._closed = False
        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._screens_changed)
            app.screenRemoved.connect(self._screens_changed)
            app.primaryScreenChanged.connect(self._screens_changed)
            for screen in app.screens():
                self._watch_screen(screen)

    def _watch_screen(self, screen):
        screen.geometryChanged.connect(self._queue_rebuild)
        screen.logicalDotsPerInchChanged.connect(self._queue_rebuild)

    def _queue_rebuild(self, *_args):
        if self._closed or self._rebuild_queued:
            return
        self._rebuild_queued = True
        def rebuild():
            self._rebuild_queued = False
            if not self._closed and not self._region.isNull():
                self._rebuild()
        QTimer.singleShot(0, rebuild)

    # ------------------------------------------------------------------
    def region(self) -> QRect:
        return QRect(self._region)

    def surfaces(self) -> tuple[OverlayWindow, ...]:
        return tuple(self._surfaces)

    def winIds(self) -> tuple[int, ...]:
        return tuple(int(surface.winId()) for surface in self._surfaces)

    def ensure_platform_setup(self) -> None:
        for surface in self._surfaces:
            surface.ensure_platform_setup()

    def is_capture_excluded(self) -> bool:
        return bool(self._surfaces) and all(s.is_capture_excluded() for s in self._surfaces)

    def geometry(self) -> QRect:
        return QRect(self._region)

    # ------------------------------------------------------------------
    def set_region(self, rect: QRect) -> None:
        self._region = QRect(rect)
        self._canvas.set_region(QRect(QPoint(0, 0), rect.size()))
        self._rebuild()

    def _targets(self) -> list[tuple[object, QRect]]:
        return surface_pieces(self._region, QGuiApplication.screens())

    def _rebuild(self) -> None:
        blocks = list(self._canvas._blocks)
        targets = self._targets()
        existing = {surface.screen(): surface for surface in self._surfaces}
        kept = []
        for screen, piece in targets:
            surface = existing.pop(screen, None)
            if surface is None:
                surface = OverlayWindow(self.s)
            surface.setScreen(screen)
            origin = piece.topLeft() - self._region.topLeft()
            surface.set_surface(piece, origin, self._region.size())
            surface.winId()
            surface.ensure_platform_setup()
            if self._visible:
                surface.show()
                surface.raise_()
            kept.append(surface)
        for surface in existing.values():
            surface.close()
            surface.deleteLater()
        self._surfaces = kept
        self._areas = {}
        self.set_blocks(blocks)
        self.surfaces_changed.emit()

    def _screens_changed(self, _screen=None) -> None:
        if _screen is not None and _screen in QGuiApplication.screens():
            self._watch_screen(_screen)
        self._queue_rebuild()

    # ------------------------------------------------------------------
    def _sync_areas(self) -> None:
        union = set()
        for surface in self._surfaces:
            origin = surface._region_origin
            piece = surface.geometry()
            left, top = origin.x(), origin.y()
            right, bottom = left + piece.width(), top + piece.height()
            clipped = []
            for x, y, w, h in surface.capture_areas():
                x0, y0 = max(left, x), max(top, y)
                x1, y1 = min(right, x + w), min(bottom, y + h)
                if x1 > x0 and y1 > y0:
                    clipped.append((x0, y0, x1 - x0, y1 - y0))
            self._areas[surface] = clipped
            union.update(clipped)
        self.capture_areas_changed.emit(sorted(union))

    def set_blocks(self, blocks: list[dict]) -> None:
        self._canvas.set_blocks(blocks)
        for surface in self._surfaces:
            origin = surface._region_origin
            surface._blocks = blocks
            surface._layout = [(r.translated(-origin.x(), -origin.y()), *rest)
                               for r, *rest in self._canvas._layout]
            surface.update()
        self._sync_areas()

    def clear_blocks(self) -> None:
        self._canvas.clear_blocks()
        for surface in self._surfaces:
            surface.blockSignals(True)
            surface.clear_blocks()
            surface.blockSignals(False)
        self._areas = {}
        self.capture_areas_changed.emit([])

    def refresh_style(self) -> None:
        self._canvas.refresh_style()
        self.set_blocks(self._canvas._blocks)
        for surface in self._surfaces:
            surface.update()

    def flash_border(self, on: bool) -> None:
        for surface in self._surfaces:
            surface.flash_border(on)

    def setVisible(self, visible: bool) -> None:
        self._visible = bool(visible)
        for surface in self._surfaces:
            surface.setVisible(self._visible)
            if self._visible:
                surface.raise_()

    def show(self) -> None:
        self.setVisible(True)

    def hide(self) -> None:
        self.setVisible(False)

    def isVisible(self) -> bool:
        return self._visible

    def close(self) -> None:
        self._closed = True
        self._visible = False
        self._canvas.close()
        for surface in self._surfaces:
            surface.close()
            surface.deleteLater()
        self._surfaces = []
        self._areas = {}
