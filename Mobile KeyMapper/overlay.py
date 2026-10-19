"""Layer over the video that draws the control markers and, in edit mode, lets you drag them."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..mapping import layout_edit as le
from ..mapping.profile import ALSO_MODES, PINCH_MODES, TWO_POINT_MODES, Binding, Look, Profile, Stick
from ..video.widget import VideoWidget
from . import theme
from .label_layout import place_labels

RADIUS = 20

# a tiny tag on the marker that says what the key does when it is not a plain tap / hold
MODE_BADGE = {"toggle": "on/off", "repeat": "auto", "double": "x2", "swipe": "\u2192", "drag": "\u21e2",
              "pinch-out": "+", "pinch-in": "\u2212", "sequence": "1-2-3"}
_MODIFIER_SHORT = {"Ctrl": "Ct", "Shift": "Sh", "Alt": "Al"}


def short_label(name: str) -> str:
    """Text inside a marker: wheel directions as arrows, combinations abbreviated (Shift+W -> Sh+W)."""
    base = name.rsplit("+", 1)[-1] if "+" in name and not name.endswith("+") else name
    prefix = name[: len(name) - len(base)]
    for long, short in _MODIFIER_SHORT.items():
        prefix = prefix.replace(long, short)
    if base.startswith("Wheel"):
        base = "\u25b2" if base == "WheelUp" else "\u25bc"
    text = prefix + base
    return text if len(text) <= 6 else text[:5] + "\u2026"


class MarkerOverlay(QWidget):
    editChanged = Signal()                    # a drag finished: save the profile
    selectionChanged = Signal(object)         # le.Hit | None
    rebindRequested = Signal(object)          # double-click on a marker
    contextRequested = Signal(object, QPoint)  # right-click on a marker (hit, global position)

    def __init__(self, video: VideoWidget) -> None:
        super().__init__(video)
        self._video = video
        self.edit = False
        self.edit_profile: Profile | None = None
        self.selection: le.Hit | None = None
        self.preview: tuple[float, float] | None = None      # where a new button is about to be created
        self._drag: le.DragState | None = None
        self._passthrough = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bindings: list[Binding] = []
        self.sticks: list[Stick] = []
        self.looks: list[Look] = []
        self.captured = False
        self.pressed: set[str] = set()
        self.selected = -1
        self.active = False
        self.banner = ""
        self.opacity = 1.0                      # of the markers while key mapping is on (0 = invisible)
        self._toast = ""
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(1400)
        self._toast_timer.timeout.connect(lambda: self.show_toast(""))
        self.setGeometry(video.rect())
        video.installEventFilter(self)
        video.frameSizeChanged.connect(lambda *_: self.update())
        self.raise_()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._video and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._video.rect())
        return False

    def set_state(self, bindings: list[Binding], active: bool, sticks: list[Stick] | None = None,
                  looks: list[Look] | None = None) -> None:
        self.bindings, self.active, self.sticks = bindings, active, sticks or []
        self.looks = looks or []
        self.update()

    def set_preview(self, pos) -> None:
        """One spot (tuple), several spots (list of tuples) or None."""
        self.preview = pos
        self.update()

    def set_opacity(self, value: float) -> None:
        self.opacity = max(0.0, min(1.0, float(value)))
        self.update()

    def effective_opacity(self) -> float:
        """Markers fade only while playing; while setting up or editing they are always fully visible."""
        return self.opacity if (self.active and not self.edit) else 1.0

    def show_toast(self, text: str) -> None:
        """A short message at the bottom of the picture (always readable, even at 0 % opacity)."""
        self._toast = text
        if text:
            self._toast_timer.start()
        self.update()

    def set_captured(self, captured: bool) -> None:
        self.captured = captured
        self.update()

    def set_pressed(self, pressed: set[str]) -> None:
        self.pressed = pressed
        self.update()

    def set_selected(self, index: int) -> None:
        self.selected = index
        self.update()

    # -- layout editing ----------------------------------------------------------------------
    def set_edit(self, on: bool, profile: Profile | None = None) -> None:
        self.edit = on
        self.edit_profile = profile if on else None
        self._drag = None
        if not on:
            self.selection = None
        self._apply_mouse_mode()
        self.update()

    def set_passthrough(self, passthrough: bool) -> None:
        """While a key is being captured, let mouse clicks reach the video so they can be bound."""
        self._passthrough = passthrough
        self._apply_mouse_mode()

    def _apply_mouse_mode(self) -> None:
        interactive = self.edit and not self._passthrough
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not interactive)
        self.setMouseTracking(interactive)

    def select(self, hit: "le.Hit | None") -> None:
        self.selection = hit
        self.update()
        self.selectionChanged.emit(hit)

    def _norm(self, pos) -> tuple[float, float] | None:
        target = self._video.target_rect()
        if target.isEmpty():
            return None
        return ((pos.x() - target.x()) / target.width(), (pos.y() - target.y()) / target.height())

    def _hit_at(self, pos) -> "le.Hit | None":
        norm, target = self._norm(pos), self._video.target_rect()
        if norm is None or self.edit_profile is None:
            return None
        return le.hit_test(self.edit_profile, norm[0], norm[1], target.width(), target.height())

    def mousePressEvent(self, event) -> None:
        if not (self.edit and self.edit_profile is not None):
            return super().mousePressEvent(event)
        hit = self._hit_at(event.position())
        self.select(hit)
        norm = self._norm(event.position())
        if event.button() == Qt.MouseButton.LeftButton and hit is not None and norm is not None:
            self._drag = le.begin_drag(self.edit_profile, hit, *norm)
        elif event.button() == Qt.MouseButton.RightButton and hit is not None:
            self.contextRequested.emit(hit, event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if not (self.edit and self.edit_profile is not None):
            return super().mouseMoveEvent(event)
        norm, target = self._norm(event.position()), self._video.target_rect()
        if self._drag is not None and norm is not None:
            le.update_drag(self.edit_profile, self._drag, norm[0], norm[1], target.width(), target.height())
            self.update()
            return
        hit = self._hit_at(event.position())
        if hit is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif hit.kind == "look" and hit.part in ("tl", "br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif hit.kind == "look" and hit.part in ("tr", "bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif hit.kind == "stick" and hit.part not in ("center", ""):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag is not None:
            self._drag = None
            self.editChanged.emit()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.edit and self.edit_profile is not None:
            hit = self._hit_at(event.position())
            if hit is not None and hit.kind != "look":
                self._drag = None
                self.rebindRequested.emit(hit)
            return
        super().mouseDoubleClickEvent(event)

    def set_banner(self, text: str) -> None:
        self.banner = text
        self.update()

    def _paint_also(self, painter: QPainter, target: QRectF, b: Binding, index: int, cx: float, cy: float,
                    fill: QColor, edge: QColor) -> None:
        """The extra spots one key touches together with its main spot: a small marker joined by a dashed line."""
        radius = RADIUS * 0.75
        for k, (ax, ay) in enumerate(b.also):
            px = target.x() + ax * target.width()
            py = target.y() + ay * target.height()
            painter.setPen(QPen(QColor(255, 255, 255, 130), 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(cx, cy), QPointF(px, py))
            picked = (self.selection is not None and self.selection.kind == "tap" and self.selection.index == index
                      and self.selection.part == f"also{k}")
            painter.setPen(QPen(QColor(theme.WARN) if picked else edge, 2))
            painter.setBrush(QColor(theme.WARN) if picked else fill)
            painter.drawEllipse(QRectF(px - radius, py - radius, radius * 2, radius * 2))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(px - radius, py - radius, radius * 2, radius * 2), Qt.AlignmentFlag.AlignCenter,
                             short_label(b.input))

    def _paint_badge(self, painter: QPainter, cx: float, cy: float, text: str, scope: bool) -> None:
        tags = ([text] if text else []) + (["aim"] if scope else [])
        label = " ".join(tags)
        font = painter.font()
        small = QFont(font)
        small.setPointSize(7)
        painter.setFont(small)
        width = painter.fontMetrics().horizontalAdvance(label) + 8
        box = QRectF(cx + RADIUS * 0.45, cy - RADIUS - 8, width, 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.WARN))
        painter.drawRoundedRect(box, 7, 7)
        painter.setPen(QColor("#1b1200"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
        painter.setFont(font)

    def _paint_extras(self, painter: QPainter, target: QRectF, b: Binding, cx: float, cy: float) -> None:
        """Second point of a swipe / drag, the extra points of a multi-tap, the two fingers of a pinch."""
        w, h = target.width(), target.height()
        accent = QColor(theme.ACCENT if self.active else "#8a93a8")
        accent.setAlpha(220)
        if b.mode in TWO_POINT_MODES and b.x2 is not None:
            ex, ey = target.x() + b.x2 * w, target.y() + b.y2 * h
            painter.setPen(QPen(accent, 3))
            painter.drawLine(QPointF(cx, cy), QPointF(ex, ey))
            angle = math.atan2(ey - cy, ex - cx)
            tip = QPointF(ex, ey)
            head = QPolygonF([tip, QPointF(ex - 14 * math.cos(angle - 0.45), ey - 14 * math.sin(angle - 0.45)),
                              QPointF(ex - 14 * math.cos(angle + 0.45), ey - 14 * math.sin(angle + 0.45))])
            painter.setBrush(accent)
            painter.drawPolygon(head)
            painter.setBrush(QColor(15, 18, 24, 200))
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(QRectF(ex - 9, ey - 9, 18, 18))
        elif b.mode == "sequence":
            previous = QPointF(cx, cy)
            for number, (sx, sy, _delay) in enumerate(b.steps[1:], 2):
                point = QPointF(target.x() + sx * w, target.y() + sy * h)
                painter.setPen(QPen(accent, 2, Qt.PenStyle.DashLine))
                painter.drawLine(previous, point)
                painter.setBrush(accent)
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.drawEllipse(QRectF(point.x() - 11, point.y() - 11, 22, 22))
                painter.setPen(QColor("#ffffff"))
                painter.drawText(QRectF(point.x() - 11, point.y() - 11, 22, 22), Qt.AlignmentFlag.AlignCenter,
                                 str(number))
                previous = point
        elif b.mode in PINCH_MODES:
            far = b.span * min(w, h)
            near = far * 0.4
            outwards = b.mode == "pinch-out"
            painter.setPen(QPen(accent, 3))
            for sign in (-1, 1):
                a, z = (near, far) if outwards else (far, near)
                painter.drawLine(QPointF(cx + sign * a, cy), QPointF(cx + sign * z, cy))
                painter.setBrush(QColor(15, 18, 24, 200))
                painter.drawEllipse(QRectF(cx + sign * z - 7, cy - 7, 14, 14))

    def _paint_look(self, painter: QPainter, target: QRectF, look: Look) -> None:
        zone = QRectF(target.x() + look.x0 * target.width(), target.y() + look.y0 * target.height(),
                      (look.x1 - look.x0) * target.width(), (look.y1 - look.y0) * target.height())
        color = QColor(theme.OK if self.captured else (theme.ACCENT if self.active else "#5b6378"))
        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        fill = QColor(color)
        fill.setAlpha(28)
        painter.setBrush(fill)
        painter.drawRoundedRect(zone, 10, 10)
        if self.edit:                                       # corner handles for resizing
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor(theme.WARN if self.selection and self.selection.kind == "look" else color))
            for cx, cy in ((zone.left(), zone.top()), (zone.right(), zone.top()),
                           (zone.left(), zone.bottom()), (zone.right(), zone.bottom())):
                painter.drawRect(QRectF(cx - 6, cy - 6, 12, 12))
            painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            painter.setBrush(fill)
        centre = zone.center()
        painter.setPen(QPen(color, 2))
        painter.drawLine(int(centre.x() - 9), int(centre.y()), int(centre.x() + 9), int(centre.y()))
        painter.drawLine(int(centre.x()), int(centre.y() - 9), int(centre.x()), int(centre.y() + 9))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(zone.x(), zone.y() + 4, zone.width(), 16), Qt.AlignmentFlag.AlignCenter,
                         look.label + ("  (mouse captured)" if self.captured else ""))

    def _paint_stick(self, painter: QPainter, target: QRectF, stick: Stick) -> None:
        cx = target.x() + stick.x * target.width()
        cy = target.y() + stick.y * target.height()
        radius = stick.radius * min(target.width(), target.height())
        ring = QColor(theme.ACCENT if self.active else "#5b6378")
        ring.setAlpha(150)
        painter.setPen(QPen(ring, 3))
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        offsets = {"up": (0, -radius), "down": (0, radius), "left": (-radius, 0), "right": (radius, 0)}
        for direction, (dx, dy) in offsets.items():
            key = stick.keys[direction]
            held = key in self.pressed
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor(theme.OK) if held else ring)
            painter.drawEllipse(QRectF(cx + dx - 14, cy + dy - 14, 28, 28))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(cx + dx - 14, cy + dy - 14, 28, 28), Qt.AlignmentFlag.AlignCenter,
                             key if len(key) <= 3 else key[:2] + "…")
        if stick.label:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(cx - 60, cy + radius + 16, 120, 16), Qt.AlignmentFlag.AlignCenter, stick.label)
        if self.edit and self.selection and self.selection.kind == "stick":
            painter.setPen(QPen(QColor(theme.WARN), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - radius - 5, cy - radius - 5, radius * 2 + 10, radius * 2 + 10))

    def paintEvent(self, _event) -> None:
        target = self._video.target_rect()
        if target.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", 8)
        font.setBold(True)
        painter.setFont(font)
        alpha = self.effective_opacity()
        painter.setOpacity(alpha)
        if alpha < 0.01:
            self._paint_toast(painter)
            return
        for look in self.looks:
            self._paint_look(painter, target, look)
        for stick in self.sticks:
            self._paint_stick(painter, target, stick)
        metrics = painter.fontMetrics()
        texts = []
        for binding in self.bindings:
            label = binding.label
            if label and metrics.horizontalAdvance(label) > 120:
                label = metrics.elidedText(label, Qt.TextElideMode.ElideRight, 120)
            texts.append(label)
        centers = [(target.x() + b.x * target.width(), target.y() + b.y * target.height())
                   for b in self.bindings]
        label_rects = place_labels(
            [(cx, cy, metrics.horizontalAdvance(t) + 10 if t else 0) for (cx, cy), t in zip(centers, texts)],
            height=16, radius=RADIUS, bounds=(self.width(), self.height()))
        for index, binding in enumerate(self.bindings):
            cx = target.x() + binding.x * target.width()
            cy = target.y() + binding.y * target.height()
            self._paint_extras(painter, target, binding, cx, cy)
            picked = (self.selection is not None and self.selection.kind == "tap" and self.selection.index == index)
            if binding.input in self.pressed:
                fill, edge = QColor(theme.OK), QColor("#ffffff")
            elif picked or index == self.selected:
                fill, edge = QColor(theme.WARN), QColor("#ffffff")
            else:
                base = QColor(theme.ACCENT if self.active else "#5b6378")
                base.setAlpha(170)
                fill, edge = base, QColor(255, 255, 255, 200)
            if binding.mode in ALSO_MODES and binding.also:
                self._paint_also(painter, target, binding, index, cx, cy, fill, edge)
            painter.setPen(QPen(edge, 2))
            painter.setBrush(fill)
            painter.drawEllipse(QRectF(cx - RADIUS, cy - RADIUS, RADIUS * 2, RADIUS * 2))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(cx - RADIUS, cy - RADIUS, RADIUS * 2, RADIUS * 2),
                             Qt.AlignmentFlag.AlignCenter, short_label(binding.input))
            badge = MODE_BADGE.get(binding.mode)
            if badge or binding.scope:
                self._paint_badge(painter, cx, cy, badge or "", binding.scope)
            rect = label_rects[index]
            if rect is not None:
                box = QRectF(*rect)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 150))
                painter.drawRoundedRect(box, 4, 4)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(box, Qt.AlignmentFlag.AlignCenter, texts[index])
        if self.preview is not None:                       # the spot(s) the user just clicked for a new button
            points = self.preview if isinstance(self.preview, list) else [self.preview]
            previous = None
            for number, (fx, fy) in enumerate(points, 1):
                px = target.x() + fx * target.width()
                py = target.y() + fy * target.height()
                if previous is not None:
                    painter.setPen(QPen(QColor(theme.WARN), 2, Qt.PenStyle.DashLine))
                    painter.drawLine(QPointF(*previous), QPointF(px, py))
                painter.setPen(QPen(QColor(theme.WARN), 3, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(255, 176, 32, 60))
                painter.drawEllipse(QRectF(px - RADIUS, py - RADIUS, RADIUS * 2, RADIUS * 2))
                painter.setPen(QColor("#ffffff"))
                painter.drawText(QRectF(px - RADIUS, py - RADIUS, RADIUS * 2, RADIUS * 2),
                                 Qt.AlignmentFlag.AlignCenter, str(number) if len(points) > 1 else "?")
                previous = (px, py)
        if self.banner:
            font.setPointSize(10)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            width = metrics.horizontalAdvance(self.banner) + 28
            box = QRectF((self.width() - width) / 2, 10, width, 28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(15, 18, 24, 220))
            painter.drawRoundedRect(box, 14, 14)
            painter.setPen(QColor(theme.OK if self.active else "#ffffff"))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self.banner)
        self._paint_toast(painter)

    def _paint_toast(self, painter: QPainter) -> None:
        if not self._toast:
            return
        painter.setOpacity(1.0)
        font = QFont("Segoe UI", 11)
        font.setBold(True)
        painter.setFont(font)
        width = painter.fontMetrics().horizontalAdvance(self._toast) + 36
        box = QRectF((self.width() - width) / 2, self.height() - 64, width, 34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 18, 24, 230))
        painter.drawRoundedRect(box, 17, 17)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self._toast)
