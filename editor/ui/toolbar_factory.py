from typing import Dict

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QColor
from PySide6.QtWidgets import QToolBar, QToolButton

from .styles import ModernColors, tools_toolbar_style
from .color_widgets import ColorButton
from .icon_factory import (
    ICON_SIZE,
    make_icon_rect,
    make_icon_ellipse,
    make_icon_line,
    make_icon_arrow,
    make_icon_pencil,
    make_icon_text,
    make_icon_blur,
    make_icon_eraser,
    make_icon_select,
)


def create_tools_toolbar(window, canvas):
    tools_tb = QToolBar("Tools")
    tools_tb.setOrientation(Qt.Vertical)
    tools_tb.setMovable(False)
    tools_tb.setFloatable(False)
    window.addToolBar(Qt.LeftToolBarArea, tools_tb)

    tool_buttons = []

    def add_tool(tool, icon, tooltip):
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setFixedSize(52, 52)
        btn.clicked.connect(lambda checked, t=tool: canvas.set_tool(t))
        tools_tb.addWidget(btn)
        tool_buttons.append(btn)
        return btn

    add_tool("select", make_icon_select(), "Выделение")
    add_tool("rect", make_icon_rect(), "Прямоугольник")
    add_tool("ellipse", make_icon_ellipse(), "Эллипс")
    add_tool("line", make_icon_line(), "Линия")
    add_tool("arrow", make_icon_arrow(), "Стрелка")
    add_tool("free", make_icon_pencil(), "Карандаш")
    add_tool("blur", make_icon_blur(), "Блюр")
    add_tool("erase", make_icon_eraser(), "Ластик")
    add_tool("text", make_icon_text(), "Текст")

    tool_buttons[0].setChecked(True)
    canvas.set_tool("select")

    tools_tb.setStyleSheet(tools_toolbar_style())
    return tool_buttons


def create_actions_toolbar(window, canvas):
    tb = QToolBar("Actions")
    tb.setMovable(False)
    tb.setFloatable(False)
    window.addToolBar(tb)

    def add_action(text, fn, checkable=False, sc=None, icon_text="", show_text=False):
        a = QAction(text, window)
        a.setCheckable(checkable)
        if sc:
            a.setShortcut(QKeySequence(sc))
        window.addAction(a)
        a.setShortcutContext(Qt.WindowShortcut)
        a.triggered.connect(fn if checkable else (lambda _checked=False: fn()))
        btn = QToolButton()
        btn.setDefaultAction(a)
        if show_text:
            btn.setText(f"{icon_text} {text}" if icon_text and text else (text or icon_text))
        else:
            btn.setText(icon_text)
            btn.setToolTip(text)
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addWidget(btn)
        return a, btn

    color_btn = ColorButton(QColor(ModernColors.PRIMARY))
    color_btn.setToolTip("Цвет")
    color_btn.clicked.connect(window.choose_color)
    tb.addWidget(color_btn)

    tb.addSeparator()

    actions: Dict[str, QAction] = {}
    actions['live'], _ = add_action("Live", window.toggle_live_text, sc="Ctrl+L", icon_text="🔍", show_text=False)
    actions['live_copy'], _ = add_action("Текст", window.copy_live_text, sc="Ctrl+Shift+C", icon_text="📄", show_text=False)
    actions['ocr'], _ = add_action("OCR", window.ocr_current, sc="Ctrl+Alt+O", icon_text="📄", show_text=False)
    actions['new'], _ = add_action("Новый снимок", window.add_screenshot, sc="Ctrl+N", icon_text="📸", show_text=False)
    actions['collage'], _ = add_action("Коллаж", window.open_collage, sc="Ctrl+K", icon_text="🧩", show_text=False)
    add_action("Копировать", window.copy_to_clipboard, sc="Ctrl+C", icon_text="📋", show_text=False)
    add_action("Сохранить", window.save_image, sc="Ctrl+S", icon_text="💾", show_text=False)
    add_action("Отмена", lambda: canvas.undo(), sc="Ctrl+Z", icon_text="↶", show_text=False)

    return color_btn, actions
