# -*- coding: utf-8 -*-
from typing import Optional
import math
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import (
    QFont,
    QColor,
    QTextCursor,
    QTextCharFormat,
    QPen,
    QPainter,
)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsTextItem,
                               QGraphicsItemGroup)


class EditableTextItem(QGraphicsTextItem):
    """Улучшенный текстовый элемент с лучшим управлением цветом и редактированием"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._text_color = QColor(255, 80, 80)
        self._font = QFont("Montserrat", 18)
        self._is_editing = False
        self._placeholder_text = "Введите текст..."
        self._ignore_content_changes = False  # Флаг для предотвращения рекурсии

        # Параметры для изменения масштаба
        self._resizing = False
        self._resize_start_pos = QPointF()
        self._resize_start_scale = 1.0
        self._resize_origin = QPointF()

        # Настройка элемента
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)

        # Устанавливаем начальные параметры
        self.setFont(self._font)
        self.setDefaultTextColor(self._text_color)

        if not text:
            self.setPlainText(self._placeholder_text)
            self._select_all_text()

        # Подключаем сигналы для отслеживания изменений
        self.document().contentsChanged.connect(self._on_text_changed)

    def _select_all_text(self):
        """Выделить весь текст"""
        try:
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            self.setTextCursor(cursor)
        except Exception:
            pass

    def _on_text_changed(self):
        """Обработчик изменения текста"""
        # Предотвращаем рекурсивные вызовы
        if self._ignore_content_changes:
            return

        # Применяем цвет ко всему тексту при изменении, но только если это не placeholder
        current_text = self.toPlainText()
        if current_text and current_text != self._placeholder_text:
            self._apply_color_to_all_text()

    def _apply_color_to_all_text(self):
        """Применить текущий цвет ко всему тексту"""
        try:
            self._ignore_content_changes = True

            # Получаем текущий курсор и сохраняем его позицию
            current_cursor = self.textCursor()
            cursor_position = current_cursor.position()

            # Создаем новый курсор для форматирования
            format_cursor = QTextCursor(self.document())
            format_cursor.select(QTextCursor.SelectionType.Document)

            # Создаем формат с нужным цветом
            char_format = QTextCharFormat()
            char_format.setForeground(self._text_color)

            # Применяем формат
            format_cursor.mergeCharFormat(char_format)

            # Восстанавливаем позицию курсора
            current_cursor.setPosition(min(cursor_position, self.document().characterCount() - 1))
            self.setTextCursor(current_cursor)

        except Exception as e:
            print(f"Ошибка при применении цвета к тексту: {e}")
        finally:
            self._ignore_content_changes = False

    def set_text_color(self, color: QColor):
        """Установить цвет текста"""
        self._text_color = color
        self.setDefaultTextColor(color)

        # Применяем цвет только если текст не является placeholder
        current_text = self.toPlainText()
        if current_text and current_text != self._placeholder_text:
            self._apply_color_to_all_text()

    def set_font(self, font: QFont):
        """Установить шрифт"""
        self._font = font
        self.setFont(font)

        # Применяем шрифт ко всему тексту
        try:
            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.SelectionType.Document)
            char_format = QTextCharFormat()
            char_format.setFont(font)
            cursor.mergeCharFormat(char_format)
        except Exception as e:
            print(f"Ошибка при применении шрифта: {e}")

    def _toggle_format(self, mode: str):
        """Переключить форматирование текста"""
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
        """Обработчик получения фокуса"""
        super().focusInEvent(event)
        self._is_editing = True

        # Если текст это placeholder, очищаем и выделяем
        if self.toPlainText() == self._placeholder_text:
            self.setPlainText("")

    def focusOutEvent(self, event):
        """Обработчик потери фокуса"""
        super().focusOutEvent(event)
        self._is_editing = False

        # Если текст пустой, возвращаем placeholder
        current_text = self.toPlainText().strip()
        if not current_text:
            self._ignore_content_changes = True
            self.setPlainText(self._placeholder_text)
            self._ignore_content_changes = False
            self._select_all_text()

    def keyPressEvent(self, event):
        """Обработчик нажатий клавиш"""
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

        # Если нажат Escape, убираем фокус
        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            return

        # Если нажат Enter без Shift, убираем фокус (завершаем редактирование)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.clearFocus()
            return

        super().keyPressEvent(event)

    def paint(self, painter, option, widget=None):
        """Переопределяем отрисовку для лучшего отображения"""
        # Если элемент выделен и не редактируется, рисуем рамку
        if self.isSelected() and not self._is_editing:
            painter.save()

            # Рисуем рамку выделения
            rect = self.boundingRect()
            pen = QPen(QColor(70, 130, 240), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 8, 8)

            # Рисуем маленькие квадратики по углам для изменения размера
            handle_size = 6
            handles = [
                rect.topLeft(),
                rect.topRight(),
                rect.bottomLeft(),
                rect.bottomRight()
            ]

            painter.setBrush(QColor(70, 130, 240))
            painter.setPen(QPen(QColor(255, 255, 255), 1))

            for handle_pos in handles:
                handle_rect = QRectF(
                    handle_pos.x() - handle_size / 2,
                    handle_pos.y() - handle_size / 2,
                    handle_size,
                    handle_size
                )
                painter.drawRoundedRect(handle_rect, 2, 2)

            painter.restore()

        super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_editing:
            rect = self.boundingRect()
            handle_size = 6
            handles = [
                rect.topLeft(),
                rect.topRight(),
                rect.bottomLeft(),
                rect.bottomRight(),
            ]
            for handle in handles:
                handle_rect = QRectF(
                    handle.x() - handle_size / 2,
                    handle.y() - handle_size / 2,
                    handle_size,
                    handle_size,
                )
                if handle_rect.contains(event.pos()):
                    self._resizing = True
                    self._resize_start_pos = event.pos()
                    self._resize_start_scale = self.scale()
                    self._resize_origin = rect.center()
                    self.setTransformOriginPoint(rect.center())
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            start_vec = self._resize_start_pos - self._resize_origin
            current_vec = event.pos() - self._resize_origin
            start_len = math.hypot(start_vec.x(), start_vec.y())
            current_len = math.hypot(current_vec.x(), current_vec.y())
            if start_len > 0:
                new_scale = self._resize_start_scale * (current_len / start_len)
                self.setScale(max(0.1, new_scale))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing and event.button() == Qt.LeftButton:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TextManager:
    """Класс для управления текстовыми элементами на канвасе"""

    def __init__(self, canvas):
        self.canvas = canvas
        self._font = QFont("Montserrat", 18)
        self._text_color = QColor(255, 80, 80)
        self._current_text_item = None

    def set_text_color(self, color: QColor):
        """Установить цвет для нового текста"""
        self._text_color = color

        # Применяем к текущему редактируемому элементу
        if self._current_text_item:
            self._current_text_item.set_text_color(color)

    def create_text_item(self, pos: QPointF, text: str = "") -> EditableTextItem:
        """Создать новый текстовый элемент на канвасе"""
        # Завершаем редактирование предыдущего элемента
        if self._current_text_item:
            self._current_text_item.clearFocus()

        # Создаем новый элемент
        item = EditableTextItem(text)
        item.set_font(self._font)
        item.set_text_color(self._text_color)
        item.setPos(pos)

        # Добавляем на сцену
        self.canvas.scene.addItem(item)

        # Устанавливаем как текущий
        self._current_text_item = item

        # Даем фокус для начала редактирования
        item.setFocus(Qt.MouseFocusReason)
        item.setSelected(True)

        return item

    def apply_color_to_selected(self, selected_items, focus_item=None):
        """Применить текущий цвет к выделенным текстовым элементам"""
        targets = list(selected_items)
        if isinstance(focus_item, EditableTextItem) and focus_item not in targets:
            targets.append(focus_item)

        for item in targets:
            if isinstance(item, (QGraphicsTextItem, EditableTextItem)):
                if hasattr(item, 'set_text_color'):
                    item.set_text_color(self._text_color)
                else:
                    item.setDefaultTextColor(self._text_color)
                    # Безопасно применяем цвет ко всему существующему тексту
                    try:
                        cursor = QTextCursor(item.document())
                        cursor.select(QTextCursor.SelectionType.Document)
                        fmt = QTextCharFormat()
                        fmt.setForeground(self._text_color)
                        cursor.mergeCharFormat(fmt)
                    except Exception as e:
                        print(f"Ошибка при применении цвета к элементу: {e}")


    def finish_current_editing(self):
        """Завершить редактирование текущего текстового элемента"""
        if self._current_text_item:
            self._current_text_item.clearFocus()
            self._current_text_item = None
