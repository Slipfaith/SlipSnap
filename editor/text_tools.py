# -*- coding: utf-8 -*-
from PySide6.QtCore import QPointF, Qt, QRectF, QSizeF
from PySide6.QtGui import (
    QFont,
    QColor,
    QTextCursor,
    QTextCharFormat,
    QPen,
    QPainter,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QMenu,
)
from .undo_commands import RemoveCommand


RESIZE_HANDLE_SIZE = 6


class EditableTextItem(QGraphicsTextItem):
    """Улучшенный текстовый элемент с лучшим управлением цветом и редактированием"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._text_color = QColor(255, 80, 80)
        self._font = QFont("Montserrat", 18)
        self._is_editing = False
        self._placeholder_text = "Введите текст..."
        self._ignore_content_changes = False  # Флаг для предотвращения рекурсии

        # Параметры для изменения размера текстового блока
        self._resizing = False
        self._resize_start_pos = QPointF()
        self._resize_start_rect = QRectF()
        self._resize_handle = None
        self._resize_start_font_size = self._font.pointSizeF()

        # Настройка элемента
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setAcceptHoverEvents(True)

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
        self._is_editing = self.textInteractionFlags() != Qt.NoTextInteraction

        # Если текст это placeholder, очищаем при начале редактирования
        if self._is_editing and self.toPlainText() == self._placeholder_text:
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

        # После завершения редактирования возвращаем обычный режим
        self.setTextInteractionFlags(Qt.NoTextInteraction)

    def keyPressEvent(self, event):
        """Обработчик нажатий клавиш"""
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

        # Если нажат Escape, убираем фокус
        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            return

        # Если нажат Enter без Shift, убираем фокус (завершаем редактирование)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.clearFocus()
            return

        super().keyPressEvent(event)

    def boundingRect(self):
        rect = super().boundingRect()
        margin = RESIZE_HANDLE_SIZE / 2
        return rect.adjusted(-margin, -margin, margin, margin)

    def paint(self, painter, option, widget=None):
        """Переопределяем отрисовку для лучшего отображения"""
        # Если элемент выделен, рисуем рамку
        if self.isSelected():
            painter.save()

            # Рисуем рамку выделения
            rect = super().boundingRect()
            pen = QPen(QColor(70, 130, 240), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 8, 8)

            # Рисуем квадраты для изменения размера в углах
            handle_size = RESIZE_HANDLE_SIZE
            handle_positions = [
                rect.topLeft(),
                rect.topRight(),
                rect.bottomLeft(),
                rect.bottomRight(),
            ]

            painter.setBrush(QColor(70, 130, 240))
            painter.setPen(QPen(QColor(255, 255, 255), 1))

            for handle_pos in handle_positions:
                handle_rect = QRectF(
                    handle_pos.x() - handle_size / 2,
                    handle_pos.y() - handle_size / 2,
                    handle_size,
                    handle_size,
                )
                painter.drawRoundedRect(handle_rect, 2, 2)

            painter.restore()

        super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            rect = super().boundingRect()
            handle_size = RESIZE_HANDLE_SIZE
            handles = {
                "top-left": rect.topLeft(),
                "top-right": rect.topRight(),
                "bottom-left": rect.bottomLeft(),
                "bottom-right": rect.bottomRight(),
            }
            for name, handle in handles.items():
                handle_rect = QRectF(
                    handle.x() - handle_size / 2,
                    handle.y() - handle_size / 2,
                    handle_size,
                    handle_size,
                )
                if handle_rect.contains(event.pos()):
                    self._resizing = True
                    self._resize_handle = name
                    self._resize_start_pos = event.pos()
                    self._resize_start_rect = rect
                    self._resize_start_font_size = self._font.pointSizeF()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def hoverMoveEvent(self, event):
        rect = super().boundingRect()
        handle_size = RESIZE_HANDLE_SIZE
        handles = {
            "top-left": rect.topLeft(),
            "top-right": rect.topRight(),
            "bottom-left": rect.bottomLeft(),
            "bottom-right": rect.bottomRight(),
        }
        for name, handle in handles.items():
            handle_rect = QRectF(
                handle.x() - handle_size / 2,
                handle.y() - handle_size / 2,
                handle_size,
                handle_size,
            )
            if handle_rect.contains(event.pos()):
                if name in ("top-left", "bottom-right"):
                    self.setCursor(Qt.SizeFDiagCursor)
                else:
                    self.setCursor(Qt.SizeBDiagCursor)
                return
        self.setCursor(Qt.IBeamCursor if self._is_editing else Qt.ArrowCursor)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.IBeamCursor if self._is_editing else Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_handle:
            delta = event.pos() - self._resize_start_pos
            w0 = self._resize_start_rect.width()
            h0 = self._resize_start_rect.height()

            if self._resize_handle == "bottom-right":
                scale_w = (w0 + delta.x()) / w0
                scale_h = (h0 + delta.y()) / h0
                scale = max(scale_w, scale_h, 20 / w0, 20 / h0)
                new_x = self.x()
                new_y = self.y()
            elif self._resize_handle == "bottom-left":
                scale_w = (w0 - delta.x()) / w0
                scale_h = (h0 + delta.y()) / h0
                scale = max(scale_w, scale_h, 20 / w0, 20 / h0)
                new_x = self.x() + (w0 - w0 * scale)
                new_y = self.y()
            elif self._resize_handle == "top-right":
                scale_w = (w0 + delta.x()) / w0
                scale_h = (h0 - delta.y()) / h0
                scale = max(scale_w, scale_h, 20 / w0, 20 / h0)
                new_x = self.x()
                new_y = self.y() + (h0 - h0 * scale)
            else:  # top-left
                scale_w = (w0 - delta.x()) / w0
                scale_h = (h0 - delta.y()) / h0
                scale = max(scale_w, scale_h, 20 / w0, 20 / h0)
                new_x = self.x() + (w0 - w0 * scale)
                new_y = self.y() + (h0 - h0 * scale)

            new_width = w0 * scale
            new_height = h0 * scale

            self.prepareGeometryChange()
            self.setPos(new_x, new_y)
            self.setTextWidth(new_width)
            self.document().setPageSize(QSizeF(new_width, new_height))

            new_font = QFont(self._font)
            new_font.setPointSizeF(max(1.0, self._resize_start_font_size * scale))
            self.set_font(new_font)

            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing and event.button() == Qt.LeftButton:
            self._resizing = False
            self._resize_handle = None
            self.setCursor(Qt.IBeamCursor if self._is_editing else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setTextInteractionFlags(Qt.TextEditorInteraction)
            self._is_editing = True
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_delete = menu.addAction("Удалить")
        chosen = menu.exec(event.screenPos())
        event.accept()
        if chosen == act_delete:
            scene = self.scene()
            if scene:
                view = scene.views()[0] if scene.views() else None
                undo_stack = getattr(view, "undo_stack", None)
                if undo_stack:
                    undo_stack.push(RemoveCommand(scene, self))
                else:
                    scene.removeItem(self)


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
