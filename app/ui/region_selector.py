"""
Tam ekran yarı saydam katman: fareyle sürükleyerek çevrilecek bölgeyi seçme.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RegionSelector(QWidget):
    region_selected = Signal(QRect)   # global mantıksal koordinat
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        geo = QRect()
        for s in QGuiApplication.screens():
            geo = geo.united(s.geometry())
        self.setGeometry(geo)

        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._done = False

    def start(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _selection(self) -> QRect | None:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    # ------------------------------------------------------------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        sel = self._selection()
        if sel is not None:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(sel, Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.fillRect(sel, QColor(0, 150, 255, 25))   # tamamen 0 alfa olmasın
            p.setPen(QPen(QColor(0, 170, 255), 2))
            p.drawRect(sel)
            p.setPen(QColor(255, 255, 255))
            p.drawText(sel.topLeft() + QPoint(4, -6), f"{sel.width()} × {sel.height()}")
        else:
            p.setPen(QColor(255, 255, 255))
            f = p.font()
            f.setPointSize(16)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "çevrilecek alanı fareyle sürükleyerek seçin  •  iptal: esc")
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.position().toPoint()
            self._current = self._origin
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self._cancel()

    def mouseMoveEvent(self, e) -> None:
        if self._origin is not None:
            self._current = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._current = e.position().toPoint()
        sel = self._selection()
        if sel is not None and sel.width() > 30 and sel.height() > 30:
            self._done = True
            global_rect = sel.translated(self.geometry().topLeft())
            self.close()
            self.region_selected.emit(global_rect)
        else:
            self._origin = self._current = None
            self.update()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self._cancel()

    def _cancel(self) -> None:
        if not self._done:
            self._done = True
            self.close()
            self.cancelled.emit()
