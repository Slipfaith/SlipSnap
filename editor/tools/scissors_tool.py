# -*- coding: utf-8 -*-
"""Scissors: cut screenshots along a torn line and delete separated pieces."""

import math
import random
import re
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QUndoCommand,
)
from PySide6.QtWidgets import QGraphicsPixmapItem, QMenu

from .base_tool import BaseTool

CUTTABLE_TAGS = {"screenshot", "meme"}

# Torn line shape, in scene units (screenshot pixels at 100% item scale):
# a slow wander, a mid-size ragged rhythm and fine fibre-level grit.
TEAR_STEP = 2.0
TEAR_OCTAVES = ((34.0, 4.0), (10.0, 1.8), (3.0, 0.7))  # (wavelength, amplitude)
# A cut ending this close to an edge is extended past it, so a stroke that
# stops just short of the border still separates the piece.
EDGE_SNAP = 24.0

# Paper rim along the kept edge: a light under-layer, a white core, fibres
# sticking out of the tear and a soft shadow cast onto the hole.
PAPER_SHADE = QColor(226, 224, 218)
PAPER_WHITE = QColor(253, 253, 250)
RIM_WIDTH = (2.5, 9.0)  # min/max band width in pixels
SHADOW_COLOR = QColor(0, 0, 0, 120)
SHADOW_OFFSET = (2, 3)
SHADOW_SOFTNESS = 4

_RUN_RE = re.compile(rb"\xff+")
_INVERT = bytes(255 - i for i in range(256))


def cuttable_item(item) -> bool:
    return isinstance(item, QGraphicsPixmapItem) and item.data(0) in CUTTABLE_TAGS


class _Noise1D:
    """Smooth 1-D value noise in [-1, 1] (cosine-interpolated random knots)."""

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._knots: List[float] = []

    def __call__(self, x: float) -> float:
        i = int(math.floor(x))
        while len(self._knots) <= i + 1:
            self._knots.append(self._rng.uniform(-1.0, 1.0))
        t = x - i
        t = (1 - math.cos(t * math.pi)) * 0.5
        return self._knots[i] * (1 - t) + self._knots[i + 1] * t


def _resample(points: List[QPointF], step: float) -> List[Tuple[QPointF, float, float, float]]:
    """Points every ``step`` along a polyline as (point, distance, normal_x, normal_y)."""
    out: List[Tuple[QPointF, float, float, float]] = []
    travelled = 0.0
    carry = 0.0
    for a, b in zip(points, points[1:]):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        seg = math.hypot(dx, dy)
        if seg < 1e-6:
            continue
        nx, ny = -dy / seg, dx / seg
        if not out:
            out.append((QPointF(a), 0.0, nx, ny))
        dist = step - carry
        while dist <= seg:
            t = dist / seg
            out.append((QPointF(a.x() + dx * t, a.y() + dy * t), travelled + dist, nx, ny))
            dist += step
        carry = seg - (dist - step)
        travelled += seg
    if out and len(points) > 1:
        last = points[-1]
        _p, _d, nx, ny = out[-1]
        out.append((QPointF(last), travelled, nx, ny))
    return out


def tear_polyline(points: List[QPointF], seed: Optional[int] = None) -> List[QPointF]:
    """Resample a stroke and displace it sideways so it reads as a paper tear."""
    if len(points) < 2:
        return list(points)
    rng = random.Random(seed)
    octaves = [(_Noise1D(rng), wavelength, amp) for wavelength, amp in TEAR_OCTAVES]
    out: List[QPointF] = []
    for p, dist, nx, ny in _resample(points, TEAR_STEP):
        offset = sum(noise(dist / wavelength) * amp for noise, wavelength, amp in octaves)
        out.append(QPointF(p.x() + nx * offset, p.y() + ny * offset))
    return out


def _extend_to_edge(poly: List[QPointF], rect: QRectF) -> List[QPointF]:
    """Push stroke ends that stop near the item's border out past it."""
    if len(poly) < 2:
        return poly
    result = list(poly)
    for end_idx, step in ((0, 1), (len(result) - 1, -1)):
        end = result[end_idx]
        # Direction from a point a little way back along the stroke.
        back_idx = end_idx + step * min(5, len(result) - 1)
        back = result[back_idx]
        dx, dy = end.x() - back.x(), end.y() - back.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        tip = QPointF(end.x() + dx / length * EDGE_SNAP, end.y() + dy / length * EDGE_SNAP)
        if not rect.contains(tip):
            if end_idx == 0:
                result.insert(0, tip)
            else:
                result.append(tip)
    return result


class PieceMap:
    """Connected regions of a pixmap separated by cut lines (pixel space)."""

    def __init__(self, width: int, height: int, blade_bytes: bytes, stride: int):
        self.width = width
        self.height = height
        self.blade_bytes = blade_bytes
        self.stride = stride
        self._parent: List[int] = []
        self.rows: List[List[Tuple[int, int, int]]] = []
        self._label(blade_bytes, stride)
        self.sizes: Dict[int, int] = {}
        for row in self.rows:
            for s, e, rid in row:
                root = self._find(rid)
                self.sizes[root] = self.sizes.get(root, 0) + (e - s)

    def _find(self, i: int) -> int:
        parent = self._parent
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _label(self, data: bytes, stride: int) -> None:
        # Run-based labelling with 4-connectivity: an aliased 1px cut line
        # (8-connected) is enough of a wall between two pieces.
        prev: List[Tuple[int, int, int]] = []
        parent = self._parent
        for y in range(self.height):
            row = data[y * stride:y * stride + self.width]
            cur: List[Tuple[int, int, int]] = []
            j = 0
            for m in _RUN_RE.finditer(row):
                s, e = m.span()
                rid = len(parent)
                parent.append(rid)
                while j < len(prev) and prev[j][1] <= s:
                    j += 1
                k = j
                while k < len(prev) and prev[k][0] < e:
                    a, b = self._find(rid), self._find(prev[k][2])
                    if a != b:
                        parent[a] = b
                    k += 1
                cur.append((s, e, rid))
            self.rows.append(cur)
            prev = cur

    def label_at(self, x: int, y: int) -> Optional[int]:
        if not (0 <= y < self.height and 0 <= x < self.width):
            return None
        for s, e, rid in self.rows[y]:
            if s <= x < e:
                return self._find(rid)
        return None

    def is_separate(self, label: int) -> bool:
        """True when the cuts actually split ``label`` off from the rest."""
        total = sum(self.sizes.values())
        return self.sizes.get(label, 0) < total - max(16, total // 1000)

    def piece_mask(self, label: int) -> QImage:
        """Alpha mask of one piece: opaque inside, transparent elsewhere."""
        w = self.width
        buf = bytearray(w * self.height)
        for y, row in enumerate(self.rows):
            base = y * w
            for s, e, rid in row:
                if self._find(rid) == label:
                    buf[base + s:base + e] = b"\xff" * (e - s)
        return QImage(bytes(buf), w, self.height, w, QImage.Format_Alpha8).copy()

    def blade_mask(self) -> QImage:
        inverted = self.blade_bytes.translate(_INVERT)
        return QImage(inverted, self.width, self.height, self.stride, QImage.Format_Alpha8).copy()


def _dilate(mask: QImage, radius: int) -> QImage:
    """Square dilation of an alpha mask (separable: rows, then columns)."""
    src = mask.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    if radius <= 0:
        return src
    horiz = QImage(src.size(), QImage.Format_ARGB32_Premultiplied)
    horiz.fill(Qt.transparent)
    p = QPainter(horiz)
    for dx in range(-radius, radius + 1):
        p.drawImage(dx, 0, src)
    p.end()
    out = QImage(src.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    for dy in range(-radius, radius + 1):
        p.drawImage(0, dy, horiz)
    p.end()
    return out


def _tinted(mask: QImage, color: QColor) -> QImage:
    img = mask.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(img.rect(), color)
    p.end()
    return img


def _blurred(image: QImage, softness: int) -> QImage:
    """Cheap blur: shrink, then scale back up smoothly."""
    if softness <= 1:
        return image
    w, h = image.width(), image.height()
    small = image.scaled(max(1, w // softness), max(1, h // softness),
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def _band_polygon(samples, rng: random.Random, scale: float) -> QPolygonF:
    """Ragged band around a cut whose width drifts independently on each side."""
    lo, hi = RIM_WIDTH
    sides = []
    for _side in (1, -1):
        slow, fast = _Noise1D(rng), _Noise1D(rng)
        widths = []
        for _p, dist, _nx, _ny in samples:
            n = 0.75 * slow(dist / 26.0) + 0.25 * fast(dist / 5.0)
            widths.append((lo + (hi - lo) * (0.5 + 0.5 * n)) * scale)
        sides.append(widths)
    left = [QPointF(p.x() + nx * w, p.y() + ny * w) for (p, _d, nx, ny), w in zip(samples, sides[0])]
    right = [QPointF(p.x() - nx * w, p.y() - ny * w) for (p, _d, nx, ny), w in zip(samples, sides[1])]
    return QPolygonF(left + right[::-1])


def tear_out_piece(
    image: QImage,
    piece: QImage,
    blade: QImage,
    cuts: Optional[List[List[QPointF]]] = None,
    seed: int = 0,
) -> QImage:
    """Make ``piece`` transparent and dress the remaining edge as torn paper.

    All images and ``cuts`` (polylines) are in the same pixel space; ``piece``
    and ``blade`` are alpha masks. The cut line itself is removed where it
    borders the piece, so no one-pixel seam of the old image is left behind.
    """
    result = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    rng = random.Random(seed)

    removed = _dilate(piece, 1)
    p = QPainter(removed)
    p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    p.drawImage(0, 0, blade)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.drawImage(0, 0, piece)
    p.end()

    p = QPainter(result)
    p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    p.drawImage(0, 0, removed)
    p.end()

    # Paper rim: a shaded under-layer with a whiter core on top, each with its
    # own ragged inner edge. Limited to the neighbourhood of the hole and
    # painted only onto pixels that remain (SourceAtop keeps the hole clear).
    rim = QImage(result.size(), QImage.Format_ARGB32_Premultiplied)
    rim.fill(Qt.transparent)
    fibres = QImage(result.size(), QImage.Format_ARGB32_Premultiplied)
    fibres.fill(Qt.transparent)
    rp = QPainter(rim)
    rp.setRenderHint(QPainter.Antialiasing, True)
    rp.setPen(Qt.NoPen)
    fp = QPainter(fibres)
    fp.setRenderHint(QPainter.Antialiasing, True)
    for poly in cuts or []:
        samples = _resample(poly, 1.5)
        if len(samples) < 2:
            continue
        rp.setBrush(PAPER_SHADE)
        rp.drawPolygon(_band_polygon(samples, rng, 1.0))
        rp.setBrush(PAPER_WHITE)
        rp.drawPolygon(_band_polygon(samples, rng, 0.55))
        # Loose fibres poking out of the tear on both sides; the ones over
        # kept pixels are dropped below, leaving hairs over the hole only.
        for pt, _dist, nx, ny in samples:
            if rng.random() > 0.45:
                continue
            side = 1 if rng.random() < 0.5 else -1
            length = rng.uniform(1.5, 5.0)
            angle = rng.uniform(-0.6, 0.6)
            dx = (nx * math.cos(angle) - ny * math.sin(angle)) * side * length
            dy = (nx * math.sin(angle) + ny * math.cos(angle)) * side * length
            colour = QColor(PAPER_WHITE)
            colour.setAlpha(rng.randint(120, 230))
            fp.setPen(QPen(colour, rng.uniform(0.6, 1.2), Qt.SolidLine, Qt.RoundCap))
            fp.drawLine(pt, QPointF(pt.x() + dx, pt.y() + dy))
    rp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    rp.drawImage(0, 0, _dilate(removed, int(math.ceil(RIM_WIDTH[1])) + 1))
    rp.end()
    fp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    fp.drawImage(0, 0, removed)
    fp.end()

    # Soft shadow of the kept paper falling onto the hole.
    shadow = QImage(result.size(), QImage.Format_ARGB32_Premultiplied)
    shadow.fill(Qt.transparent)
    sp = QPainter(shadow)
    sp.drawImage(SHADOW_OFFSET[0], SHADOW_OFFSET[1], _tinted(result, SHADOW_COLOR))
    sp.end()
    shadow = _blurred(shadow, SHADOW_SOFTNESS)
    sp = QPainter(shadow)
    sp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    sp.drawImage(0, 0, removed)
    sp.end()

    p = QPainter(result)
    p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
    p.drawImage(0, 0, rim)
    p.setCompositionMode(QPainter.CompositionMode_DestinationOver)
    p.drawImage(0, 0, shadow)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    p.drawImage(0, 0, fibres)
    p.end()
    return result


class ScissorsTool(BaseTool):
    """Draw torn cut lines across screenshots; right-click a piece to delete it."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.cursor = QCursor(Qt.CrossCursor)
        self._stroke: List[QPointF] = []
        # item -> cut polylines in the item's local coordinates
        self._cuts: Dict[QGraphicsPixmapItem, List[List[QPointF]]] = {}
        self._piece_cache: Dict[QGraphicsPixmapItem, Tuple[tuple, PieceMap]] = {}
        self._highlight: Optional[Tuple[QGraphicsPixmapItem, QImage]] = None

    # ---- drawing cuts ------------------------------------------------------
    def press(self, pos: QPointF):
        self._stroke = [QPointF(pos)]
        self.canvas.viewport().update()

    def move(self, pos: QPointF):
        if not self._stroke:
            return
        last = self._stroke[-1]
        if math.hypot(pos.x() - last.x(), pos.y() - last.y()) >= 1.5:
            self._stroke.append(QPointF(pos))
            self.canvas.viewport().update()

    def release(self, pos: QPointF):
        stroke = self._stroke
        self._stroke = []
        if stroke:
            stroke.append(QPointF(pos))
        self.canvas.viewport().update()
        if self._stroke_length(stroke) < 8:
            return
        torn = tear_polyline(stroke, seed=hash(tuple((round(p.x()), round(p.y())) for p in stroke)))
        added: Dict[QGraphicsPixmapItem, List[QPointF]] = {}
        for item in self.canvas.scene.items():
            if not cuttable_item(item) or not item.isVisible():
                continue
            inverse, ok = item.sceneTransform().inverted()
            if not ok:
                continue
            local = [inverse.map(p) for p in torn]
            rect = item.boundingRect()
            if not QPolygonF(local).boundingRect().intersects(rect):
                continue
            if not any(rect.contains(p) for p in local):
                continue
            added[item] = _extend_to_edge(local, rect)
        if added:
            self.canvas.undo_stack.push(_AddCutsCommand(self, added))

    @staticmethod
    def _stroke_length(points: List[QPointF]) -> float:
        return sum(math.hypot(b.x() - a.x(), b.y() - a.y()) for a, b in zip(points, points[1:]))

    def add_cut(self, item, polyline: List[QPointF]) -> None:
        self._cuts.setdefault(item, []).append(polyline)
        self._piece_cache.pop(item, None)
        self.canvas.viewport().update()

    def remove_cut(self, item, polyline: List[QPointF]) -> None:
        cuts = self._cuts.get(item, [])
        if polyline in cuts:
            cuts.remove(polyline)
        if not cuts:
            self._cuts.pop(item, None)
        self._piece_cache.pop(item, None)
        self.canvas.viewport().update()

    def clear(self) -> None:
        """Forget all cuts (the scene was replaced)."""
        self._stroke = []
        self._cuts.clear()
        self._piece_cache.clear()
        self._highlight = None

    def cuts_for(self, item) -> List[List[QPointF]]:
        return list(self._cuts.get(item, []))

    # ---- pieces ------------------------------------------------------------
    def piece_map(self, item) -> Optional[PieceMap]:
        cuts = self._cuts.get(item)
        pixmap = item.pixmap()
        if not cuts or pixmap.isNull():
            return None
        key = (pixmap.width(), pixmap.height(), pixmap.devicePixelRatio(), len(cuts), id(cuts[-1]))
        cached = self._piece_cache.get(item)
        if cached is not None and cached[0] == key:
            return cached[1]
        blade = QImage(pixmap.width(), pixmap.height(), QImage.Format_Grayscale8)
        blade.fill(255)
        p = QPainter(blade)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.scale(pixmap.devicePixelRatio(), pixmap.devicePixelRatio())
        pen = QPen(QColor(0, 0, 0), 0)  # cosmetic: exactly one pixel wide
        p.setPen(pen)
        for poly in cuts:
            p.drawPolyline(QPolygonF(poly))
        p.end()
        pieces = PieceMap(blade.width(), blade.height(), bytes(blade.constBits()), blade.bytesPerLine())
        self._piece_cache[item] = (key, pieces)
        return pieces

    def _pixel_at(self, item, scene_pos: QPointF) -> Tuple[int, int]:
        local = item.mapFromScene(scene_pos)
        dpr = item.pixmap().devicePixelRatio()
        return int(math.floor(local.x() * dpr)), int(math.floor(local.y() * dpr))

    def item_at(self, scene_pos: QPointF):
        for item in self.canvas.scene.items(scene_pos):
            if cuttable_item(item):
                return item
        return None

    def delete_piece_at(self, item, scene_pos: QPointF) -> bool:
        pieces = self.piece_map(item)
        if pieces is None:
            return False
        label = pieces.label_at(*self._pixel_at(item, scene_pos))
        if label is None or not pieces.is_separate(label):
            return False
        before = QPixmap(item.pixmap())
        source = before.toImage()
        dpr = before.devicePixelRatio()
        cuts_px = [[QPointF(pt.x() * dpr, pt.y() * dpr) for pt in poly] for poly in self._cuts.get(item, [])]
        torn = tear_out_piece(
            source,
            pieces.piece_mask(label),
            pieces.blade_mask(),
            cuts_px,
            seed=label,
        )
        torn.setDevicePixelRatio(before.devicePixelRatio())
        after = QPixmap.fromImage(torn)
        self.canvas.undo_stack.push(_TearPieceCommand(item, before, after))
        return True

    # ---- context menu ------------------------------------------------------
    @staticmethod
    def _exec_menu(menu: QMenu, global_pos):
        return menu.exec(global_pos)

    def show_context_menu(self, scene_pos: QPointF, global_pos) -> None:
        item = self.item_at(scene_pos)
        if item is None:
            return
        pieces = self.piece_map(item)
        label = None
        if pieces is not None:
            label = pieces.label_at(*self._pixel_at(item, scene_pos))
        separable = label is not None and pieces.is_separate(label)

        menu = QMenu(self.canvas)
        act_delete = menu.addAction("Удалить кусок")
        act_delete.setEnabled(separable)
        if not separable:
            act_delete.setToolTip("Проведите разрез через весь снимок, чтобы отделить кусок")
            if pieces is None:
                act_delete.setText("Удалить кусок — сначала сделайте разрез")
            else:
                act_delete.setText("Удалить кусок — разрез не отделяет его")
        act_clear = menu.addAction("Убрать разрезы на этом снимке")
        act_clear.setEnabled(bool(self._cuts.get(item)))

        if separable:
            tint = QColor(220, 53, 69, 90)
            self._highlight = (item, _tinted(pieces.piece_mask(label), tint))
            self.canvas.viewport().update()
        try:
            chosen = self._exec_menu(menu, global_pos)
        finally:
            self._highlight = None
            self.canvas.viewport().update()

        if chosen is act_delete and separable:
            if self.delete_piece_at(item, scene_pos):
                self.canvas.set_tool("select")
        elif chosen is act_clear:
            cuts = self._cuts.get(item, [])
            if cuts:
                self.canvas.undo_stack.push(_ClearCutsCommand(self, item, list(cuts)))

    # ---- overlay -----------------------------------------------------------
    def paint_overlay(self, painter: QPainter) -> None:
        """Draw cut lines and the piece highlight; painter is in scene coords."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        scene = self.canvas.scene
        if self._highlight is not None:
            item, tint = self._highlight
            if item.scene() is scene:
                painter.save()
                painter.setTransform(item.sceneTransform(), True)
                dpr = item.pixmap().devicePixelRatio() or 1.0
                painter.drawImage(QRectF(0, 0, tint.width() / dpr, tint.height() / dpr), tint)
                painter.restore()

        under = QPen(QColor(255, 255, 255, 220), 3)
        under.setCosmetic(True)
        over = QPen(QColor(30, 30, 30, 230), 1, Qt.DashLine)
        over.setCosmetic(True)
        for item, cuts in self._cuts.items():
            if item.scene() is not scene or not item.isVisible():
                continue
            transform = item.sceneTransform()
            for poly in cuts:
                scene_poly = transform.map(QPolygonF(poly))
                painter.setPen(under)
                painter.drawPolyline(scene_poly)
                painter.setPen(over)
                painter.drawPolyline(scene_poly)

        if len(self._stroke) > 1:
            painter.setPen(under)
            painter.drawPolyline(QPolygonF(self._stroke))
            painter.setPen(over)
            painter.drawPolyline(QPolygonF(self._stroke))
        painter.restore()


class _AddCutsCommand(QUndoCommand):
    def __init__(self, tool: ScissorsTool, cuts: Dict[QGraphicsPixmapItem, List[QPointF]]):
        super().__init__("Разрез")
        self._tool = tool
        self._cuts = cuts

    def redo(self):
        for item, poly in self._cuts.items():
            self._tool.add_cut(item, poly)

    def undo(self):
        for item, poly in self._cuts.items():
            self._tool.remove_cut(item, poly)


class _ClearCutsCommand(QUndoCommand):
    def __init__(self, tool: ScissorsTool, item, cuts: List[List[QPointF]]):
        super().__init__("Убрать разрезы")
        self._tool = tool
        self._item = item
        self._cuts = cuts

    def redo(self):
        for poly in self._cuts:
            self._tool.remove_cut(self._item, poly)

    def undo(self):
        for poly in self._cuts:
            self._tool.add_cut(self._item, poly)


class _TearPieceCommand(QUndoCommand):
    def __init__(self, item, before: QPixmap, after: QPixmap):
        super().__init__("Удалить кусок")
        self._item = item
        self._before = before
        self._after = after

    def redo(self):
        self._item.setPixmap(self._after)

    def undo(self):
        self._item.setPixmap(self._before)
