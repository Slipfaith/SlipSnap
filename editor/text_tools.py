# -*- coding: utf-8 -*-
from typing import Optional
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QInputDialog, QFontDialog
from PySide6.QtCore import Qt


class TextManager:
    """Класс для управления текстовыми элементами на канвасе"""

    def __init__(self, canvas):
        self.canvas = canvas
        self._font = QFont("Arial", 18)
        self._text_color = QColor(40, 40, 40)

    def set_font(self, font: QFont):
        """Установить шрифт для нового текста"""
        self._font = font

    def set_text_color(self, color: QColor):
        """Установить цвет для нового текста"""
        self._text_color = color

    def add_text_item(self, text: str, pos: QPointF) -> QGraphicsItem:
        """Добавить текстовый элемент на канвас"""
        item = QGraphicsTextItem()
        item.setFont(self._font)
        item.setDefaultTextColor(self._text_color)
        item.setPlainText(text)

        # Применяем цвет к существующему тексту явно
        cursor = QTextCursor(item.document())
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setForeground(self._text_color)
        cursor.mergeCharFormat(fmt)

        item.setPos(pos)
        item.setTextInteractionFlags(Qt.TextEditorInteraction)
        item.setFlag(QGraphicsItem.ItemIsMovable, True)
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.canvas.scene.addItem(item)
        return item

    def prompt_and_add_text(self, pos: QPointF, parent_widget) -> Optional[QGraphicsItem]:
        """Показать диалог ввода текста и добавить его на канвас"""
        text, ok = QInputDialog.getText(parent_widget, "Текст", "Введите текст:")
        if ok and text:
            return self.add_text_item(text, pos)
        return None

    def apply_font_to_selected(self, selected_items, focus_item=None):
        """Применить текущий шрифт к выделенным текстовым элементам"""
        targets = list(selected_items)
        if isinstance(focus_item, QGraphicsTextItem) and focus_item not in targets:
            targets.append(focus_item)

        for item in targets:
            if isinstance(item, QGraphicsTextItem):
                item.setFont(self._font)
                item.setDefaultTextColor(self._text_color)

    def apply_color_to_selected(self, selected_items, focus_item=None):
        """Применить текущий цвет к выделенным текстовым элементам"""
        targets = list(selected_items)
        if isinstance(focus_item, QGraphicsTextItem) and focus_item not in targets:
            targets.append(focus_item)

        for item in targets:
            if isinstance(item, QGraphicsTextItem):
                item.setDefaultTextColor(self._text_color)
                cursor = QTextCursor(item.document())
                cursor.select(QTextCursor.Document)
                fmt = QTextCharFormat()
                fmt.setForeground(self._text_color)
                cursor.mergeCharFormat(fmt)

    def choose_font(self, parent_widget, selected_items, focus_item=None):
        """Показать диалог выбора шрифта и применить к выделенным элементам"""
        font, ok = QFontDialog.getFont(self._font, parent_widget, "Выберите шрифт")
        if ok:
            self.set_font(font)
            self.apply_font_to_selected(selected_items, focus_item)
            return True
        return False
