# -*- coding: utf-8 -*-
# editor/live_ocr.py — «Live Text» поверх скриншота: выделение слов прямоугольником
from __future__ import annotations

from typing import List, Dict, Optional
from dataclasses import dataclass

from PySide6.QtCore import Qt, QRectF, QPointF, QObject, QEvent
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (
    QGraphicsRectItem, QGraphicsItemGroup, QGraphicsItem, QGraphicsView
)

import pytesseract
from PIL import Image
from logic import qimage_to_pil


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


class _WordItem(QGraphicsRectItem):
    def __init__(self, box: WordBox):
        super().__init__(QRectF(box.left, box.top, box.width, box.height))
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


class LiveTextLayer(QGraphicsItemGroup):
    """Набор бокс-айтемов, привязанных к одному QGraphicsPixmapItem."""

    def __init__(self, parent_pixmap_item: QGraphicsItem, boxes: List[WordBox]):
        super().__init__(parent=parent_pixmap_item)
        self.setHandlesChildEvents(False)
        self._items: List[_WordItem] = []
        for b in boxes:
            it = _WordItem(b)
            it.setParentItem(parent_pixmap_item)  # важная привязка к картинке
            self.addToGroup(it)
            self._items.append(it)

    def show_boxes(self, visible: bool = True):
        for it in self._items:
            it.setVisible(visible)

    def clear_selection(self):
        for it in self._items:
            it.set_active(False)

    def select_in_rect(self, rect: QRectF):
        self.clear_selection()
        for it in self._items:
            if rect.intersects(it.rect()):
                it.set_active(True)

    def selected_text(self) -> str:
        picked = [it.box for it in self._items if it.pen().color() == QColor(40, 120, 240, 255)]
        if not picked:
            return ""
        picked.sort(key=lambda b: (b.block, b.par, b.line, b.word))
        out: List[str] = []
        last_key = None
        for b in picked:
            key = (b.block, b.par, b.line)
            if last_key is None:
                out.append(b.text)
            else:
                out.append(b.text if key == last_key else "\n" + b.text)
            last_key = key
        txt = " ".join(" ".join(out).split())
        txt = txt.replace(" \n ", "\n").replace("\n ", "\n").replace(" \n", "\n")
        return txt.strip()


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
    """Перехватывает мышь на viewport, чтобы рисовать прямоугольное выделение для LiveText."""

    def __init__(self, view: QGraphicsView, manager: "LiveTextManager"):
        super().__init__(view)
        self.view = view
        self.manager = manager
        self.dragging = False
        self.start_scene = QPointF()
        self.end_scene = QPointF()
        self.rubber: Optional[QGraphicsRectItem] = None

    def eventFilter(self, obj, e):
        if not self.manager.active:
            return False
        if e.type() == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
            self.dragging = True
            self.start_scene = self.view.mapToScene(e.position().toPoint())
            self.end_scene = self.start_scene
            self._update_rubber()
            return True
        if e.type() == QEvent.MouseMove and self.dragging:
            self.end_scene = self.view.mapToScene(e.position().toPoint())
            self._update_rubber()
            return True
        if e.type() == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self._update_rubber(final=True)
            return True
        return False

    def _update_rubber(self, final: bool = False):
        scene = _get_scene(self.view)
        if scene is None:
            return
        if self.rubber is None:
            self.rubber = scene.addRect(QRectF(), QPen(QColor(70, 130, 240), 2))
            self.rubber.setZValue(1000)
        rect = QRectF(self.start_scene, self.end_scene).normalized()
        self.rubber.setRect(rect)

        layer = self.manager.layer
        if not layer:
            return
        pm_item = self.manager.pixmap_item
        inv = pm_item.sceneTransform().inverted()[0]
        rect_in_item = inv.mapRect(rect)
        layer.select_in_rect(rect_in_item)

        if final:
            scene.removeItem(self.rubber)
            self.rubber = None


class LiveTextManager:
    """Создаёт/удаляет LiveTextLayer для заданного Canvas."""

    def __init__(self, canvas: QGraphicsView, lang: str = "eng+rus"):
        self.canvas = canvas
        self.lang = lang
        self.layer: Optional[LiveTextLayer] = None
        self.pixmap_item: Optional[QGraphicsItem] = None
        self._filter = _ViewportFilter(canvas, self)
        self.active = False

    # ---------- public ----------
    def toggle(self) -> bool:
        if self.active:
            self.disable()
            return False
        return self.enable()

    def enable(self) -> bool:
        if self.active:
            return True
        pm = getattr(self.canvas, "pixmap_item", None)
        if pm is None:
            return False
        self.pixmap_item = pm

        # QImage -> PIL.Image
        qimg = pm.pixmap().toImage()
        pil_img: Image.Image = qimage_to_pil(qimg)

        # OCR → боксы слов
        data = pytesseract.image_to_data(
            pil_img, lang=self.lang, output_type=pytesseract.Output.DICT
        )
        boxes = self._collect_boxes(data)

        # Слой поверх картинки
        self.layer = LiveTextLayer(pm, boxes)
        self.layer.show_boxes(True)

        # Перехват мыши для выделения
        self.canvas.viewport().installEventFilter(self._filter)
        self.active = True
        return True

    def disable(self) -> None:
        if not self.active:
            return
        try:
            self.canvas.viewport().removeEventFilter(self._filter)
        except Exception:
            pass
        scene = _get_scene(self.canvas)
        if self.layer and scene is not None:
            for ch in list(self.layer.childItems()):
                ch.setParentItem(None)
                scene.removeItem(ch)
            try:
                scene.removeItem(self.layer)
            except Exception:
                pass
        self.layer = None
        self.pixmap_item = None
        self.active = False

    # ---------- helpers ----------
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
