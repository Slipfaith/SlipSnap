# -*- coding: utf-8 -*-
# editor/live_ocr.py — «Live Text» поверх скриншота: выделение слов прямоугольником
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from PySide6.QtCore import Qt, QRectF, QPointF, QObject, QEvent
from PySide6.QtGui import QPen, QColor, QPainterPath, QTransform
from PySide6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsView,
)

import pytesseract
from pytesseract import TesseractNotFoundError
from PIL import Image
from logic import qimage_to_pil


def _distance_to_rect(point: QPointF, rect: QRectF) -> float:
    """Евклидово расстояние от точки до прямоугольника (в координатах элемента)."""

    r = QRectF(rect).normalized()
    if r.width() <= 0 or r.height() <= 0:
        return 0.0
    if r.contains(point):
        return 0.0
    clamped_x = min(max(point.x(), r.left()), r.right())
    clamped_y = min(max(point.y(), r.top()), r.bottom())
    return math.hypot(point.x() - clamped_x, point.y() - clamped_y)


@dataclass
class WordBox:
    text: str
    left: int
    top: int
    width: int
    height: int
    block: int
    par: int
    line: int
    word: int


class _WordItem(QGraphicsPathItem):
    """Отдельное слово, подсвеченное поверх скриншота."""

    def __init__(self, box: WordBox):
        self._rect = QRectF(box.left, box.top, box.width, box.height)
        path = QPainterPath()
        path.addRoundedRect(self._rect, 4, 4)
        super().__init__(path)
        self.box = box
        self.setPen(QPen(QColor(255, 200, 0, 220), 1))
        self.setBrush(QColor(255, 230, 120, 50))
        self.setZValue(50)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setVisible(False)

    def set_active(self, active: bool):
        if active:
            self.setPen(QPen(QColor(40, 120, 240, 255), 2))
            self.setBrush(QColor(70, 130, 240, 60))
        else:
            self.setPen(QPen(QColor(255, 200, 0, 220), 1))
            self.setBrush(QColor(255, 230, 120, 50))

    def word_rect(self) -> QRectF:
        return QRectF(self._rect)


class LiveTextLayer(QGraphicsItemGroup):
    """Набор бокс-айтемов, привязанных к одному QGraphicsPixmapItem."""

    def __init__(self, parent_pixmap_item: QGraphicsItem, boxes: List[WordBox]):
        super().__init__(parent=parent_pixmap_item)
        self.setHandlesChildEvents(False)
        self._items: List[_WordItem] = []
        self._selection: List[_WordItem] = []
        for b in boxes:
            it = _WordItem(b)
            it.setParentItem(parent_pixmap_item)  # важная привязка к картинке
            self.addToGroup(it)
            self._items.append(it)

    def show_boxes(self, visible: bool = True):
        for it in self._items:
            it.setVisible(visible)

    def clear_selection(self):
        if not self._selection:
            for it in self._items:
                it.set_active(False)
        else:
            for it in self._selection:
                it.set_active(False)
        self._selection = []

    def _sorted_items(self, items: List[_WordItem]) -> List[_WordItem]:
        return sorted(items, key=lambda it: (it.box.block, it.box.par, it.box.line, it.box.word))

    def _apply_selection(self, selected: List[_WordItem]):
        selected_set = set(selected)
        for it in self._items:
            it.set_active(it in selected_set)
        self._selection = self._sorted_items(selected)

    def select_in_rect(self, rect: QRectF, min_overlap: float = 0.2) -> List[_WordItem]:
        rect = QRectF(rect)
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            self.clear_selection()
            return []

        picked: List[_WordItem] = []
        for it in self._items:
            word_rect = it.word_rect()
            inter = rect.intersected(word_rect)
            if inter.isNull():
                continue
            if inter.width() <= 0 or inter.height() <= 0:
                continue
            area_word = word_rect.width() * word_rect.height() or 1.0
            area_inter = inter.width() * inter.height()
            coverage = area_inter / area_word
            if coverage >= min_overlap or rect.contains(word_rect.center()):
                picked.append(it)

        if picked:
            self._apply_selection(picked)
        else:
            self.clear_selection()
        return picked

    def select_point(self, point: QPointF, radius: float = 18.0) -> Optional[_WordItem]:
        candidate: Optional[_WordItem] = None
        best_distance = radius
        for it in self._items:
            word_rect = it.word_rect()
            if word_rect.contains(point):
                candidate = it
                best_distance = 0.0
                break
            dist = _distance_to_rect(point, word_rect)
            if dist < best_distance:
                best_distance = dist
                candidate = it

        if candidate:
            self._apply_selection([candidate])
        else:
            self.clear_selection()
        return candidate

    def selected_text(self) -> str:
        if not self._selection:
            return ""
        boxes = [it.box for it in self._selection]
        boxes.sort(key=lambda b: (b.block, b.par, b.line, b.word))

        fragments: List[str] = []
        last_key = None
        for b in boxes:
            token = (b.text or "").strip()
            if not token:
                continue
            key = (b.block, b.par, b.line)
            if key != last_key:
                if fragments:
                    fragments.append("\n")
                fragments.append(token)
            else:
                if fragments and fragments[-1] not in ("\n", ""):
                    fragments.append(" ")
                fragments.append(token)
            last_key = key

        text = "".join(fragments)
        for punct in [",", ".", "!", "?", ":", ";", "%", "°", "»", "\u2019", "\u201d"]:
            text = text.replace(" " + punct, punct)
        for punct in ["«", "\u2018", "\u201c", "(", "[", "{"]:
            text = text.replace(punct + " ", punct)
        return text.strip()


def _get_scene(view: QGraphicsView):
    """Безопасно получаем сцену: как атрибут (.scene) или метод (.scene())."""
    sc = getattr(view, "scene", None)
    if sc is not None and not callable(sc):
        return sc
    try:
        return view.scene()
    except Exception:
        return None


class _ViewportFilter(QObject):
    """Перехватывает мышь на viewport для словаря LiveText."""

    DRAG_THRESHOLD = 3.0

    def __init__(self, view: QGraphicsView, manager: "LiveTextManager"):
        super().__init__(view)
        self.view = view
        self.manager = manager
        self.dragging = False
        self.moved = False
        self.start_scene = QPointF()
        self.end_scene = QPointF()
        self.rubber: Optional[QGraphicsPathItem] = None

    def eventFilter(self, obj, e):
        if not self.manager.active:
            return False

        if e.type() == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
            self.dragging = True
            self.moved = False
            pos = e.position().toPoint()
            scene_pos = self.view.mapToScene(pos)
            self.start_scene = scene_pos
            self.end_scene = scene_pos
            self._update_selection()
            return True

        if e.type() == QEvent.MouseMove and self.dragging:
            pos = e.position().toPoint()
            scene_pos = self.view.mapToScene(pos)
            if not self.moved:
                delta = scene_pos - self.start_scene
                if abs(delta.x()) >= self.DRAG_THRESHOLD or abs(delta.y()) >= self.DRAG_THRESHOLD:
                    self.moved = True
            self.end_scene = scene_pos
            self._update_selection()
            return True

        if (
            e.type() == QEvent.MouseButtonRelease
            and e.button() == Qt.LeftButton
            and self.dragging
        ):
            self.dragging = False
            pos = e.position().toPoint()
            self.end_scene = self.view.mapToScene(pos)
            self._update_selection(final=True)
            self.moved = False
            return True

        return False

    def _ensure_rubber(self, scene):
        if self.rubber is not None:
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(), 8, 8)
        pen = QPen(QColor(70, 130, 240, 230), 2)
        self.rubber = scene.addPath(path, pen)
        self.rubber.setBrush(QColor(70, 130, 240, 40))
        self.rubber.setZValue(1000)

    def _remove_rubber(self, scene):
        if self.rubber is None:
            return
        try:
            scene.removeItem(self.rubber)
        except Exception:
            pass
        self.rubber = None

    def _update_selection(self, final: bool = False):
        scene = _get_scene(self.view)
        if scene is None:
            return

        layer = self.manager.layer
        pm_item = self.manager.pixmap_item
        if not layer or pm_item is None:
            self._remove_rubber(scene)
            return

        inverted = pm_item.sceneTransform().inverted()
        inv: Optional[QTransform] = None
        invertible = True
        if isinstance(inverted, tuple):
            first, second = inverted
            if isinstance(first, QTransform):
                inv = first
                invertible = bool(second)
            elif isinstance(second, QTransform):
                inv = second
                invertible = bool(first)
        elif isinstance(inverted, QTransform):
            inv = inverted
        if not invertible or inv is None:
            return

        rect_scene = QRectF(self.start_scene, self.end_scene).normalized()

        if self.moved and rect_scene.width() > 0 and rect_scene.height() > 0:
            self._ensure_rubber(scene)
            path = QPainterPath()
            path.addRoundedRect(rect_scene, 8, 8)
            if self.rubber:
                self.rubber.setPath(path)
                self.rubber.setVisible(True)
            rect_in_item = inv.mapRect(rect_scene)
            layer.select_in_rect(rect_in_item)
        else:
            point_in_item = inv.map(self.end_scene)
            layer.select_point(point_in_item)
            self._remove_rubber(scene)

        if final:
            self._remove_rubber(scene)


class LiveTextManager:
    """Создаёт/удаляет LiveTextLayer для заданного Canvas."""

    def __init__(
        self,
        canvas: QGraphicsView,
        lang: str = "eng+rus",
        tesseract_cmd: Optional[str] = None,
    ):
        self.canvas = canvas
        self.lang = lang
        self.layer: Optional[LiveTextLayer] = None
        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._filter = _ViewportFilter(canvas, self)
        self.active = False
        self._tesseract_cmd: Optional[str] = None
        self.last_error: Optional[Dict[str, str]] = None
        if tesseract_cmd:
            try:
                candidate = Path(tesseract_cmd)
            except (TypeError, ValueError):
                candidate = None
            if candidate and candidate.exists():
                self.set_tesseract_cmd(str(candidate))

    # ---------- public ----------
    def toggle(self) -> bool:
        if self.active:
            self.disable()
            return False
        ok = self.enable()
        if not ok:
            self.active = False
        return ok

    def enable(self) -> bool:
        if self.active:
            return True
        pm = self._pick_pixmap_item()
        if pm is None:
            self.last_error = {"code": "no_pixmap", "message": "Нет изображения для распознавания"}
            return False
        self.pixmap_item = pm

        # QImage -> PIL.Image
        qimg = pm.pixmap().toImage()
        pil_img: Image.Image = qimage_to_pil(qimg)

        # OCR → боксы слов
        try:
            if self._tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
            data = pytesseract.image_to_data(
                pil_img, lang=self.lang, output_type=pytesseract.Output.DICT
            )
        except TesseractNotFoundError as exc:
            self.last_error = {"code": "not_found", "message": str(exc)}
            self.pixmap_item = None
            return False
        except RuntimeError as exc:
            self.last_error = {"code": "runtime", "message": str(exc)}
            self.pixmap_item = None
            return False
        except Exception as exc:
            self.last_error = {"code": "unknown", "message": str(exc)}
            self.pixmap_item = None
            return False
        boxes = self._collect_boxes(data)

        # Слой поверх картинки
        self.layer = LiveTextLayer(pm, boxes)
        self.layer.show_boxes(True)

        # Перехват мыши для выделения
        self.canvas.viewport().installEventFilter(self._filter)
        self.active = True
        self.last_error = None
        return True

    def disable(self) -> None:
        if not self.active:
            return
        try:
            self.canvas.viewport().removeEventFilter(self._filter)
        except Exception:
            pass
        scene = _get_scene(self.canvas)
        if self.layer:
            self.layer.clear_selection()
        if self.layer and scene is not None:
            for ch in list(self.layer.childItems()):
                ch.setParentItem(None)
                scene.removeItem(ch)
            try:
                scene.removeItem(self.layer)
            except Exception:
                pass
        if scene is not None and self._filter.rubber:
            try:
                scene.removeItem(self._filter.rubber)
            except Exception:
                pass
            self._filter.rubber = None
        self.layer = None
        self.pixmap_item = None
        self.active = False

    def selected_text(self) -> str:
        if self.layer:
            return self.layer.selected_text()
        return ""

    def set_tesseract_cmd(self, path: Optional[str]) -> None:
        if path:
            self._tesseract_cmd = str(path)
            pytesseract.pytesseract.tesseract_cmd = str(path)
        else:
            self._tesseract_cmd = None
            pytesseract.pytesseract.tesseract_cmd = "tesseract"

    @staticmethod
    def validate_tesseract_path(path: Path) -> bool:
        try:
            candidate = Path(path)
        except TypeError:
            return False
        if not candidate.exists() or not candidate.is_file():
            return False
        original = pytesseract.pytesseract.tesseract_cmd
        try:
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
        finally:
            pytesseract.pytesseract.tesseract_cmd = original

    # ---------- helpers ----------
    def _pick_pixmap_item(self) -> Optional[QGraphicsPixmapItem]:
        scene = _get_scene(self.canvas)
        if scene is not None:
            try:
                selected = scene.selectedItems()
            except Exception:
                selected = []
            for it in selected:
                if isinstance(it, QGraphicsPixmapItem):
                    return it
        pm_attr = getattr(self.canvas, "pixmap_item", None)
        if isinstance(pm_attr, QGraphicsPixmapItem):
            return pm_attr
        return None

    @staticmethod
    def _collect_boxes(data: Dict[str, List]) -> List[WordBox]:
        out: List[WordBox] = []
        n = len(data.get("text", []))
        for i in range(n):
            txt = (data["text"][i] or "").strip()
            conf = int(data.get("conf", [0] * n)[i] or 0)
            if not txt or conf < 0:
                continue
            try:
                out.append(WordBox(
                    text=txt,
                    left=int(data["left"][i]), top=int(data["top"][i]),
                    width=int(data["width"][i]), height=int(data["height"][i]),
                    block=int(data.get("block_num", [0]*n)[i] or 0),
                    par=int(data.get("par_num", [0]*n)[i] or 0),
                    line=int(data.get("line_num", [0]*n)[i] or 0),
                    word=int(data.get("word_num", [0]*n)[i] or 0),
                ))
            except Exception:
                pass
        return out
