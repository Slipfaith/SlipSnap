from typing import Dict

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QColor, QActionGroup
from PySide6.QtWidgets import QToolBar, QToolButton, QMenu

from .styles import ModernColors, tools_toolbar_style
from .color_widgets import ColorButton
from .icon_factory import (
    ICON_SIZE,
    make_icon_rect,
    make_icon_ellipse,
    make_icon_line,
    make_icon_arrow,
    make_icon_pencil,
    make_icon_marker,
    make_icon_text,
    make_icon_blur,
    make_icon_eraser,
    make_icon_select,
)


def enhanced_tools_toolbar_style() -> str:
    """Return enhanced stylesheet for the vertical tools toolbar with better scroll arrows."""
    return f"""
    QToolBar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ModernColors.SURFACE},
            stop:1 {ModernColors.SURFACE_VARIANT});
        border: none;
        border-right: 1px solid {ModernColors.BORDER};
        padding: 16px 8px;
        spacing: 4px;
    }}

    QToolBar QToolButton {{
        background: transparent;
        border: none;
        border-radius: 12px;
        margin: 3px 0;
        padding: 6px;
    }}

    QToolBar QToolButton:checked {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.PRIMARY},
            stop:1 {ModernColors.PRIMARY_HOVER});
        border: 1px solid {ModernColors.PRIMARY_HOVER};
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
    }}

    QToolBar QToolButton:hover {{
        background: {ModernColors.SURFACE_HOVER};
        transform: translateX(2px);
    }}

    QToolBar QToolButton:checked:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.PRIMARY_HOVER},
            stop:1 {ModernColors.PRIMARY});
    }}

    QToolBar QToolButton:pressed {{
        transform: scale(0.95);
    }}

    /* Стили для стрелок прокрутки панели инструментов */
    QToolBar QAbstractButton {{
        background: {ModernColors.SURFACE};
        border: 2px solid {ModernColors.BORDER};
        border-radius: 8px;
        margin: 2px;
        padding: 4px;
        min-width: 20px;
        min-height: 20px;
        max-width: 24px;
        max-height: 24px;
    }}

    QToolBar QAbstractButton:hover {{
        background: {ModernColors.PRIMARY_LIGHT};
        border: 2px solid {ModernColors.PRIMARY};
        color: {ModernColors.PRIMARY};
    }}

    QToolBar QAbstractButton:pressed {{
        background: {ModernColors.PRIMARY};
        color: white;
        transform: scale(0.95);
    }}

    /* Специальные стили для кнопок со стрелками */
    QToolBar QAbstractButton[accessibleName="qt_toolbar_ext_button"] {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.SURFACE},
            stop:1 {ModernColors.SURFACE_VARIANT});
        border: 2px solid {ModernColors.BORDER};
        border-radius: 10px;
        margin: 4px 2px;
        padding: 6px;
        font-weight: bold;
        color: {ModernColors.TEXT_SECONDARY};
        min-width: 28px;
        min-height: 28px;
    }}

    QToolBar QAbstractButton[accessibleName="qt_toolbar_ext_button"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.PRIMARY_LIGHT},
            stop:1 {ModernColors.SURFACE_HOVER});
        border: 2px solid {ModernColors.PRIMARY};
        color: {ModernColors.PRIMARY};
        transform: translateX(2px);
    }}

    QToolBar QAbstractButton[accessibleName="qt_toolbar_ext_button"]:pressed {{
        background: {ModernColors.PRIMARY};
        border: 2px solid {ModernColors.PRIMARY_HOVER};
        color: white;
        transform: scale(0.9);
    }}
    """


def enhanced_actions_toolbar_style() -> str:
    """Return enhanced stylesheet for the horizontal actions toolbar with better scroll arrows."""
    return f"""
    QToolBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.SURFACE},
            stop:1 {ModernColors.SURFACE_VARIANT});
        border: none;
        border-bottom: 1px solid {ModernColors.BORDER};
        spacing: 6px;
        padding: 12px 16px;
        font-weight: 500;
        font-size: 13px;
    }}

    QToolBar QToolButton {{
        background: transparent;
        border: none;
        padding: 10px 14px;
        border-radius: 10px;
        font-weight: 500;
        color: {ModernColors.TEXT_SECONDARY};
        min-width: 32px;
        min-height: 32px;
        font-size: 16px;
    }}

    QToolBar QToolButton:hover {{
        background: {ModernColors.SURFACE_HOVER};
        color: {ModernColors.TEXT_PRIMARY};
        transform: translateY(-1px);
    }}

    QToolBar QToolButton:pressed {{
        background: {ModernColors.PRIMARY_LIGHT};
        transform: translateY(0px);
    }}

    QToolBar QToolButton:checked {{
        background: {ModernColors.PRIMARY};
        color: white;
        border: 1px solid {ModernColors.PRIMARY_HOVER};
    }}

    QToolBar QToolButton:checked:hover {{
        background: {ModernColors.PRIMARY_HOVER};
    }}

    QLabel {{
        color: {ModernColors.TEXT_MUTED};
        font-size: 12px;
        font-weight: 500;
        margin: 0 6px;
    }}

    QToolBar::separator {{
        background: {ModernColors.BORDER};
        width: 1px;
        margin: 6px 12px;
    }}

    /* Стили для стрелок прокрутки горизонтальной панели */
    QToolBar QAbstractButton {{
        background: {ModernColors.SURFACE};
        border: 2px solid {ModernColors.BORDER};
        border-radius: 8px;
        margin: 2px;
        padding: 4px;
        min-width: 24px;
        min-height: 20px;
        max-width: 28px;
        max-height: 24px;
    }}

    QToolBar QAbstractButton:hover {{
        background: {ModernColors.PRIMARY_LIGHT};
        border: 2px solid {ModernColors.PRIMARY};
        color: {ModernColors.PRIMARY};
    }}

    QToolBar QAbstractButton:pressed {{
        background: {ModernColors.PRIMARY};
        color: white;
        transform: scale(0.95);
    }}

    /* Специальные стили для кнопок со стрелками горизонтальной панели */
    QToolBar QAbstractButton[accessibleName="qt_toolbar_ext_button"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ModernColors.SURFACE},
            stop:1 {ModernColors.SURFACE_VARIANT});
        border: 2px solid {ModernColors.BORDER};
        border-radius: 10px;
        margin: 2px 4px;
        padding: 6px;
        font-weight: bold;
        color: {ModernColors.TEXT_SECONDARY};
        min-width: 32px;
        min-height: 24px;
    }}

    QToolBar QAbstractButton[accessibleName="qt_toolbar_ext_button"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ModernColors.PRIMARY_LIGHT},
            stop:1 {ModernColors.SURFACE_HOVER});
        border: 2px solid {ModernColors.PRIMARY};
        color: {ModernColors.PRIMARY};
        transform: translateY(-2px);
    }}

    QToolBar QAbstractButton[accessibleName="qt_toolbar_ext_button"]:pressed {{
        background: {ModernColors.PRIMARY};
        border: 2px solid {ModernColors.PRIMARY_HOVER};
        color: white;
        transform: scale(0.9);
    }}
    """


def create_tools_toolbar(window, canvas):
    tools_tb = QToolBar("Tools")
    tools_tb.setOrientation(Qt.Vertical)
    tools_tb.setMovable(False)
    tools_tb.setFloatable(False)

    # Улучшенные настройки для отображения стрелок
    tools_tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
    tools_tb.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

    window.addToolBar(Qt.LeftToolBarArea, tools_tb)

    tool_buttons = []

    def add_tool(tool, icon, tooltip, shortcut=None):
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        btn.setToolTip(tooltip + (f" ({shortcut})" if shortcut else ""))
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setFixedSize(52, 52)
        btn.clicked.connect(lambda checked, t=tool: canvas.set_tool(t))
        tools_tb.addWidget(btn)
        tool_buttons.append(btn)
        if shortcut:
            act = QAction(window)
            act.setShortcut(QKeySequence(shortcut))
            act.setShortcutContext(Qt.WindowShortcut)
            act.triggered.connect(btn.click)
            window.addAction(act)
        return btn

    add_tool("select", make_icon_select(), "Выделение", "V")
    add_tool("rect", make_icon_rect(), "Прямоугольник", "R")
    add_tool("ellipse", make_icon_ellipse(), "Эллипс", "O")
    add_tool("line", make_icon_line(), "Линия", "L")
    add_tool("arrow", make_icon_arrow(), "Стрелка", "A")
    free_btn = add_tool("free", make_icon_pencil(), "Карандаш", "P")

    menu = QMenu(free_btn)
    grp = QActionGroup(menu)
    act_pencil = menu.addAction("Карандаш")
    act_marker = menu.addAction("Маркер")
    for act in (act_pencil, act_marker):
        act.setCheckable(True)
        grp.addAction(act)

    def _set_mode(mode: str):
        canvas.set_pen_mode(mode)
        free_btn.setIcon(make_icon_marker() if mode == "marker" else make_icon_pencil())
        act_pencil.setChecked(mode == "pencil")
        act_marker.setChecked(mode == "marker")

    act_pencil.triggered.connect(lambda: _set_mode("pencil"))
    act_marker.triggered.connect(lambda: _set_mode("marker"))

    act_pencil.setChecked(canvas.pen_mode == "pencil")
    act_marker.setChecked(canvas.pen_mode == "marker")
    free_btn.setMenu(menu)
    free_btn.setPopupMode(QToolButton.MenuButtonPopup)
    free_btn.setIcon(make_icon_marker() if canvas.pen_mode == "marker" else make_icon_pencil())

    add_tool("blur", make_icon_blur(), "Блюр", "B")
    add_tool("erase", make_icon_eraser(), "Ластик", "E")
    add_tool("text", make_icon_text(), "Текст", "T")

    tool_buttons[0].setChecked(True)
    canvas.set_tool("select")

    # Применяем улучшенные стили
    tools_tb.setStyleSheet(enhanced_tools_toolbar_style())
    return tool_buttons


def create_actions_toolbar(window, canvas):
    tb = QToolBar("Actions")
    tb.setMovable(False)
    tb.setFloatable(False)

    # Улучшенные настройки для отображения стрелок
    tb.setToolButtonStyle(Qt.ToolButtonTextOnly)

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
        btn.setToolTip(text + (f" ({sc})" if sc else ""))
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
    actions['new'], _ = add_action("Новый снимок", window.add_screenshot, sc="Ctrl+N", icon_text="📸", show_text=False)
    actions['collage'], _ = add_action("История", window.open_collage, sc="Ctrl+K", icon_text="🖼", show_text=False)
    add_action("Копировать", window.copy_to_clipboard, sc="Ctrl+C", icon_text="📋", show_text=False)
    add_action("Сохранить", window.save_image, sc="Ctrl+S", icon_text="💾", show_text=False)

    undo_act = canvas.undo_stack.createUndoAction(window, "Отмена")
    undo_act.setShortcut(QKeySequence("Ctrl+Z"))
    redo_act = canvas.undo_stack.createRedoAction(window, "Повтор")
    redo_act.setShortcut(QKeySequence("Ctrl+Y"))
    window.addAction(undo_act)
    window.addAction(redo_act)
    for act, text in ((undo_act, "↶"), (redo_act, "↷")):
        btn = QToolButton()
        btn.setDefaultAction(act)
        btn.setText(text)
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addWidget(btn)

    # Применяем улучшенные стили
    tb.setStyleSheet(enhanced_actions_toolbar_style())

    return color_btn, actions
