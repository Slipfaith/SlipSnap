# -*- coding: utf-8 -*-
from typing import Optional

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import (
    QFont,
    QColor,
    QTextCursor,
    QTextCharFormat,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QMenu,
    QStyle,
    QStyleOptionGraphicsItem,
)
from .undo_commands import RemoveCommand

from design_tokens import Typography, Palette, Metrics


class EditableTextItem(QGraphicsTextItem):
    """Улучшенный текстовый элемент с управлением цветом и редактированием."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._text_color = QColor(*Palette.TEXT_TOOL_COLOR)
        self._font = QFont(Typography.UI_FAMILY, Typography.TEXT_TOOL_DEFAULT_POINT)
        self._is_editing = False
        self._placeholder_text = "Введите текст..."
        self._ignore_content_changes = False

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setAcceptHoverEvents(True)
        self.setData(0, "text")

        self.setFont(self._font)
        self.setDefaultTextColor(self._text_color)

        if not text:
            self.setPlainText(self._placeholder_text)
            self._select_all_text()

        self.document().contentsChanged.connect(self._on_text_changed)

    def _select_all_text(self):
        try:
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            self.setTextCursor(cursor)
        except Exception:
            pass

    def _on_text_changed(self):
        if self._ignore_content_changes:
            return
        current_text = self.toPlainText()
        if current_text and current_text != self._placeholder_text:
            self._apply_color_to_all_text()

    def _apply_color_to_all_text(self):
        try:
            self._ignore_content_changes = True
            current_cursor = self.textCursor()
            cursor_position = current_cursor.position()

            format_cursor = QTextCursor(self.document())
            format_cursor.select(QTextCursor.SelectionType.Document)
            char_format = QTextCharFormat()
            char_format.setForeground(self._text_color)
            format_cursor.mergeCharFormat(char_format)

            current_cursor.setPosition(min(cursor_position, self.document().characterCount() - 1))
            self.setTextCursor(current_cursor)
        except Exception:
            pass
        finally:
            self._ignore_content_changes = False

    def set_text_color(self, color: QColor):
        self._text_color = color
        self.setDefaultTextColor(color)
        current_text = self.toPlainText()
        if current_text and current_text != self._placeholder_text:
            self._apply_color_to_all_text()

    def set_font(self, font: QFont):
        self._font = font
        self.setFont(font)
        try:
            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.SelectionType.Document)
            char_format = QTextCharFormat()
            char_format.setFont(font)
            cursor.mergeCharFormat(char_format)
        except Exception:
            pass

    def _toggle_format(self, mode: str):
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        current = cursor.charFormat()

        if mode == "bold":
            weight = QFont.Bold if current.fontWeight() <= QFont.Normal else QFont.Normal
            fmt.setFontWeight(weight)
        elif mode == "italic":
            fmt.setFontItalic(not current.fontItalic())
        elif mode == "underline":
            fmt.setFontUnderline(not current.fontUnderline())

        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.mergeCurrentCharFormat(fmt)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._is_editing = self.textInteractionFlags() != Qt.NoTextInteraction
        if self._is_editing and self.toPlainText() == self._placeholder_text:
            self.setPlainText("")

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._is_editing = False
        current_text = self.toPlainText().strip()
        if not current_text:
            self._ignore_content_changes = True
            self.setPlainText(self._placeholder_text)
            self._ignore_content_changes = False
            self._select_all_text()
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        # Clear any text selection so it doesn't persist as a highlight
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        if not self._is_editing and event.key() == Qt.Key_Delete:
            scene = self.scene()
            if scene:
                view = scene.views()[0] if scene.views() else None
                undo_stack = getattr(view, "undo_stack", None)
                if undo_stack:
                    undo_stack.push(RemoveCommand(scene, self))
                else:
                    scene.removeItem(self)
            event.accept()
            return

        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_B:
                self._toggle_format("bold")
                return
            if event.key() == Qt.Key_I:
                self._toggle_format("italic")
                return
            if event.key() == Qt.Key_U:
                self._toggle_format("underline")
                return

        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            return

        super().keyPressEvent(event)

    def paint(self, painter, option, widget=None):
        # Strip Qt's default dashed selection border; our overlay in
        # Canvas.drawForeground draws the selection indicator instead.
        clean = QStyleOptionGraphicsItem(option)
        clean.state &= ~QStyle.State_Selected
        super().paint(painter, clean, widget)

    def hoverMoveEvent(self, event):
        self.setCursor(Qt.IBeamCursor if self._is_editing else Qt.ArrowCursor)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setTextInteractionFlags(Qt.TextEditorInteraction)
            self._is_editing = True
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_front = menu.addAction("На передний план")
        act_back = menu.addAction("На задний план")
        menu.addSeparator()
        act_delete = menu.addAction("Удалить")
        chosen = menu.exec(event.screenPos())
        event.accept()
        scene = self.scene()
        view = scene.views()[0] if scene and scene.views() else None
        if chosen == act_front and view:
            view.bring_to_front(self)
        elif chosen == act_back and view:
            view.send_to_back(self)
        elif chosen == act_delete:
            if scene:
                undo_stack = getattr(view, "undo_stack", None)
                if undo_stack:
                    undo_stack.push(RemoveCommand(scene, self))
                else:
                    scene.removeItem(self)


class TextManager:
    """Класс для управления текстовыми элементами на канвасе."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._font = QFont(Typography.UI_FAMILY, Typography.TEXT_TOOL_DEFAULT_POINT)
        self._text_color = QColor(*Palette.TEXT_TOOL_COLOR)
        self._current_text_item = None

    def set_text_color(self, color: QColor):
        self._text_color = color
        if self._current_text_item:
            self._current_text_item.set_text_color(color)

    def create_text_item(self, pos: QPointF, text: str = "") -> EditableTextItem:
        if self._current_text_item:
            self._current_text_item.clearFocus()

        item = EditableTextItem(text)
        item.set_font(self._font)
        item.set_text_color(self._text_color)
        item.setPos(pos)

        self.canvas.scene.addItem(item)
        self.canvas.bring_to_front(item, record=False)

        self._current_text_item = item
        item.setFocus(Qt.MouseFocusReason)
        item.setSelected(True)
        return item

    def apply_color_to_selected(self, selected_items, focus_item=None):
        targets = list(selected_items)
        if isinstance(focus_item, EditableTextItem) and focus_item not in targets:
            targets.append(focus_item)

        for item in targets:
            if isinstance(item, (QGraphicsTextItem, EditableTextItem)):
                if hasattr(item, 'set_text_color'):
                    item.set_text_color(self._text_color)
                else:
                    item.setDefaultTextColor(self._text_color)
                    try:
                        cursor = QTextCursor(item.document())
                        cursor.select(QTextCursor.SelectionType.Document)
                        fmt = QTextCharFormat()
                        fmt.setForeground(self._text_color)
                        cursor.mergeCharFormat(fmt)
                    except Exception:
                        pass

    def finish_current_editing(self):
        if self._current_text_item:
            self._current_text_item.clearFocus()
            self._current_text_item = None
