from typing import Dict

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QColor, QActionGroup
from PySide6.QtWidgets import QToolBar, QToolButton, QMenu, QSlider, QLabel, QSpinBox, QDoubleSpinBox

from logic import save_config
from icons import make_icon_video

from design_tokens import Metrics

# Removed old imports from icons.py as we are using icon_factory now for consistent style
# from icons import make_icon_ocr_scan, make_icon_series

from .styles import ModernColors
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
    make_icon_zoom_lens,
    make_icon_memes,
    # New icons for top toolbar
    make_icon_new,
    make_icon_series,
    make_icon_collage,
    make_icon_ocr,
    make_icon_copy,
    make_icon_save,
    make_icon_undo,
    make_icon_redo
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
            stop:0 {ModernColors.PRIMARY_LIGHT},
            stop:1 {ModernColors.PRIMARY_LIGHT});
        border: 1px solid {ModernColors.PRIMARY_HOVER};
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
    }}

    QToolBar QToolButton:hover {{
        background: {ModernColors.SURFACE_HOVER};
        transform: translateX(2px);
    }}

    QToolBar QToolButton:checked:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.PRIMARY_LIGHT},
            stop:1 {ModernColors.PRIMARY_LIGHT});
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
        background: {ModernColors.PRIMARY_LIGHT};
        color: {ModernColors.TEXT_PRIMARY};
        border: 1px solid {ModernColors.PRIMARY_HOVER};
    }}

    QToolBar QToolButton:checked:hover {{
        background: {ModernColors.PRIMARY_LIGHT};
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
    tools_tb.setContextMenuPolicy(Qt.PreventContextMenu)

    # Улучшенные настройки для отображения стрелок
    tools_tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
    tools_tb.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

    window.addToolBar(Qt.LeftToolBarArea, tools_tb)

    tool_buttons = []
    current_shape = "rect"

    memes_btn = QToolButton()
    memes_btn.setIcon(make_icon_memes())
    memes_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    memes_btn.setToolTip("Мемы")
    memes_btn.setCheckable(False)
    memes_btn.setFixedSize(Metrics.TOOL_BUTTON, Metrics.TOOL_BUTTON)
    open_memes = getattr(window, "open_memes_dialog", None)
    if callable(open_memes):
        memes_btn.clicked.connect(open_memes)
    else:
        memes_btn.setEnabled(False)
    tools_tb.addWidget(memes_btn)
    tools_tb.addSeparator()

    def add_tool(tool, icon, tooltip, shortcut=None):
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        btn.setToolTip(tooltip + (f" ({shortcut})" if shortcut else ""))
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setFixedSize(Metrics.TOOL_BUTTON, Metrics.TOOL_BUTTON)
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
    add_tool("zoom_lens", make_icon_zoom_lens(), "Лупа", "G")
    shape_btn = QToolButton()
    shape_btn.setIcon(make_icon_rect())
    shape_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    shape_btn.setToolTip("Фигуры (R/O)")
    shape_btn.setCheckable(True)
    shape_btn.setAutoExclusive(True)
    shape_btn.setFixedSize(Metrics.TOOL_BUTTON, Metrics.TOOL_BUTTON)
    shape_btn.clicked.connect(lambda checked: canvas.set_tool(current_shape))
    tools_tb.addWidget(shape_btn)
    tool_buttons.append(shape_btn)

    shape_menu = QMenu(shape_btn)
    shape_grp = QActionGroup(shape_menu)
    act_rect = shape_menu.addAction("Прямоугольник")
    act_ellipse = shape_menu.addAction("Эллипс")
    for act in (act_rect, act_ellipse):
        act.setCheckable(True)
        shape_grp.addAction(act)
    act_rect.setChecked(True)

    def _set_shape(shape: str):
        nonlocal current_shape
        current_shape = shape
        canvas.set_tool(shape)
        shape_btn.setChecked(True)
        shape_btn.setIcon(make_icon_rect() if shape == "rect" else make_icon_ellipse())
        act_rect.setChecked(shape == "rect")
        act_ellipse.setChecked(shape == "ellipse")

    act_rect.triggered.connect(lambda: _set_shape("rect"))
    act_ellipse.triggered.connect(lambda: _set_shape("ellipse"))

    shape_btn.setContextMenuPolicy(Qt.CustomContextMenu)
    shape_btn.customContextMenuRequested.connect(lambda pos: shape_menu.exec(shape_btn.mapToGlobal(pos)))

    act_r = QAction(window)
    act_r.setShortcut(QKeySequence("R"))
    act_r.setShortcutContext(Qt.WindowShortcut)
    act_r.triggered.connect(lambda: _set_shape("rect"))
    window.addAction(act_r)

    act_o = QAction(window)
    act_o.setShortcut(QKeySequence("O"))
    act_o.setShortcutContext(Qt.WindowShortcut)
    act_o.triggered.connect(lambda: _set_shape("ellipse"))
    window.addAction(act_o)

    current_line_tool = "line"
    line_btn = QToolButton()
    line_btn.setIcon(make_icon_line())
    line_btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    line_btn.setToolTip("Линия / Стрелка (L/A)")
    line_btn.setCheckable(True)
    line_btn.setAutoExclusive(True)
    line_btn.setFixedSize(Metrics.TOOL_BUTTON, Metrics.TOOL_BUTTON)
    line_btn.clicked.connect(lambda checked: canvas.set_tool(current_line_tool))
    tools_tb.addWidget(line_btn)
    tool_buttons.append(line_btn)

    line_menu = QMenu(line_btn)
    line_grp = QActionGroup(line_menu)
    act_line = line_menu.addAction("Линия")
    act_arrow = line_menu.addAction("Стрелка")
    for act in (act_line, act_arrow):
        act.setCheckable(True)
        line_grp.addAction(act)
    act_line.setChecked(True)

    def _set_line_tool(tool: str):
        nonlocal current_line_tool
        current_line_tool = tool
        canvas.set_tool(tool)
        line_btn.setChecked(True)
        line_btn.setIcon(make_icon_line() if tool == "line" else make_icon_arrow())
        act_line.setChecked(tool == "line")
        act_arrow.setChecked(tool == "arrow")

    act_line.triggered.connect(lambda: _set_line_tool("line"))
    act_arrow.triggered.connect(lambda: _set_line_tool("arrow"))

    line_btn.setContextMenuPolicy(Qt.CustomContextMenu)
    line_btn.customContextMenuRequested.connect(lambda pos: line_menu.exec(line_btn.mapToGlobal(pos)))

    act_l = QAction(window)
    act_l.setShortcut(QKeySequence("L"))
    act_l.setShortcutContext(Qt.WindowShortcut)
    act_l.triggered.connect(lambda: _set_line_tool("line"))
    window.addAction(act_l)

    act_a = QAction(window)
    act_a.setShortcut(QKeySequence("A"))
    act_a.setShortcutContext(Qt.WindowShortcut)
    act_a.triggered.connect(lambda: _set_line_tool("arrow"))
    window.addAction(act_a)
    free_btn = add_tool("free", make_icon_pencil(), "Карандаш", "P")

    menu = QMenu(free_btn)
    grp = QActionGroup(menu)
    act_pencil = menu.addAction("Карандаш")
    act_marker = menu.addAction("Маркер")
    for act in (act_pencil, act_marker):
        act.setCheckable(True)
        grp.addAction(act)

    def _set_mode(mode: str):
        # Choosing a drawing mode from the context menu should also
        # activate the freehand tool so the user can start drawing
        # immediately with the selected instrument.
        canvas.set_tool("free")
        free_btn.setChecked(True)
        canvas.set_pen_mode(mode)
        free_btn.setIcon(make_icon_marker() if mode == "marker" else make_icon_pencil())
        act_pencil.setChecked(mode == "pencil")
        act_marker.setChecked(mode == "marker")

    act_pencil.triggered.connect(lambda: _set_mode("pencil"))
    act_marker.triggered.connect(lambda: _set_mode("marker"))

    act_pencil.setChecked(canvas.pen_mode == "pencil")
    act_marker.setChecked(canvas.pen_mode == "marker")
    free_btn.setContextMenuPolicy(Qt.CustomContextMenu)
    free_btn.customContextMenuRequested.connect(lambda pos: menu.exec(free_btn.mapToGlobal(pos)))
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
    tb.setContextMenuPolicy(Qt.PreventContextMenu)

    # Улучшенные настройки для отображения стрелок
    tb.setToolButtonStyle(Qt.ToolButtonTextOnly)

    window.addToolBar(tb)

    actions: Dict[str, QAction] = {}
    buttons: Dict[str, QToolButton] = {}

    def add_action(key, text, fn, checkable=False, sc=None, icon_text="", show_text=False, icon=None):
        a = QAction(text, window)
        a.setCheckable(checkable)
        if icon is not None:
            a.setIcon(icon)
        if sc:
            a.setShortcut(QKeySequence(sc))
        window.addAction(a)
        a.setShortcutContext(Qt.WindowShortcut)
        a.triggered.connect(fn if checkable else (lambda _checked=False: fn()))
        btn = QToolButton()
        btn.setDefaultAction(a)
        style = Qt.ToolButtonTextOnly
        if icon is not None and not show_text:
            style = Qt.ToolButtonIconOnly
            if icon_text:
                btn.setText(icon_text)
        elif show_text:
            btn.setText(f"{icon_text} {text}" if icon_text and text else (text or icon_text))
        else:
            btn.setText(icon_text)
        btn.setToolTip(text + (f" ({sc})" if sc else ""))
        btn.setToolButtonStyle(style)
        tb.addWidget(btn)
        actions[key] = a
        buttons[key] = btn
        return a, btn

    color_btn = ColorButton(QColor(ModernColors.PRIMARY))
    color_btn.setToolTip("Цвет")
    color_btn.clicked.connect(window.choose_color)
    tb.addWidget(color_btn)

    tb.addSeparator()

    # Zoom slider for canvas scaling
    zoom_slider = QSlider(Qt.Horizontal)
    zoom_slider.setRange(10, 400)
    zoom_slider.setValue(100)
    zoom_slider.setFixedWidth(Metrics.ZOOM_SLIDER_WIDTH)
    zoom_slider.setToolTip("Масштаб")
    zoom_label = QLabel("100%")
    zoom_slider.valueChanged.connect(lambda v: (canvas.set_zoom(v / 100), zoom_label.setText(f"{v}%")))
    tb.addWidget(zoom_slider)
    tb.addWidget(zoom_label)

    # Sync slider when zoom is changed via scroll wheel (without re-triggering set_zoom)
    def _on_canvas_zoom_changed(factor: float) -> None:
        pct = int(round(factor * 100))
        zoom_slider.blockSignals(True)
        zoom_slider.setValue(pct)
        zoom_slider.blockSignals(False)
        zoom_label.setText(f"{pct}%")

    canvas.zoomChanged.connect(_on_canvas_zoom_changed)

    # Zoom lens controls (active only for the zoom_lens tool)
    lens_size_label = QLabel("Лупа")
    lens_size_label.setToolTip("Размер лупы")
    lens_size_spin = QSpinBox()
    lens_size_spin.setRange(60, 260)
    lens_size_spin.setSingleStep(10)
    lens_size_spin.setSuffix(" px")
    lens_size_spin.setFixedWidth(82)
    lens_size_spin.setToolTip("Диаметр лупы")

    lens_factor_label = QLabel("x")
    lens_factor_label.setToolTip("Кратность увеличения")
    lens_factor_spin = QDoubleSpinBox()
    lens_factor_spin.setDecimals(1)
    lens_factor_spin.setRange(1.2, 8.0)
    lens_factor_spin.setSingleStep(0.2)
    lens_factor_spin.setSuffix("x")
    lens_factor_spin.setFixedWidth(72)
    lens_factor_spin.setToolTip("Увеличение лупы")

    initial_size = canvas.zoom_lens_radius()
    initial_factor = canvas.zoom_lens_factor()
    if hasattr(window, "cfg") and isinstance(window.cfg, dict):
        try:
            initial_size = int(window.cfg.get("zoom_lens_size", initial_size))
        except Exception:
            initial_size = canvas.zoom_lens_radius()
        try:
            initial_factor = float(window.cfg.get("zoom_lens_factor", initial_factor))
        except Exception:
            initial_factor = canvas.zoom_lens_factor()

    canvas.set_zoom_lens_radius(initial_size)
    canvas.set_zoom_lens_factor(initial_factor)
    lens_size_spin.setValue(canvas.zoom_lens_radius())
    lens_factor_spin.setValue(canvas.zoom_lens_factor())

    def _persist_lens_value(key: str, value) -> None:
        cfg = getattr(window, "cfg", None)
        if not isinstance(cfg, dict):
            return
        cfg[key] = value
        save_config(cfg)

    def _on_lens_size_changed(value: int) -> None:
        canvas.set_zoom_lens_radius(value)
        _persist_lens_value("zoom_lens_size", canvas.zoom_lens_radius())

    def _on_lens_factor_changed(value: float) -> None:
        canvas.set_zoom_lens_factor(value)
        _persist_lens_value("zoom_lens_factor", round(canvas.zoom_lens_factor(), 2))

    lens_size_spin.valueChanged.connect(_on_lens_size_changed)
    lens_factor_spin.valueChanged.connect(_on_lens_factor_changed)

    lens_widgets = [lens_size_label, lens_size_spin, lens_factor_label, lens_factor_spin]
    lens_widget_actions = []
    for widget in lens_widgets:
        lens_widget_actions.append(tb.addWidget(widget))

    def _single_selected_lens():
        scene = getattr(canvas, "scene", None)
        if scene is None:
            return None
        try:
            selected_items = list(scene.selectedItems())
        except RuntimeError:
            return None
        lens_items = []
        for item in selected_items:
            try:
                if str(item.data(0)).lower() == "zoom_lens":
                    lens_items.append(item)
            except RuntimeError:
                continue
        if len(selected_items) == 1 and len(lens_items) == 1:
            return lens_items[0]
        return None

    def _sync_lens_values() -> None:
        selected_lens = _single_selected_lens()
        if selected_lens is not None and hasattr(selected_lens, "radius_px") and hasattr(selected_lens, "zoom_factor"):
            try:
                size = int(selected_lens.radius_px())
            except Exception:
                size = canvas.zoom_lens_radius()
            try:
                factor = float(selected_lens.zoom_factor())
            except Exception:
                factor = canvas.zoom_lens_factor()
        else:
            size = canvas.zoom_lens_radius()
            factor = canvas.zoom_lens_factor()

        lens_size_spin.blockSignals(True)
        lens_factor_spin.blockSignals(True)
        lens_size_spin.setValue(size)
        lens_factor_spin.setValue(factor)
        lens_size_spin.blockSignals(False)
        lens_factor_spin.blockSignals(False)

    def _sync_lens_controls(*_args) -> None:
        try:
            visible = getattr(canvas, "_tool", "select") == "zoom_lens" or _single_selected_lens() is not None
            for widget in lens_widgets:
                widget.setVisible(visible)
            for action in lens_widget_actions:
                action.setVisible(visible)
            _sync_lens_values()
        except RuntimeError:
            return

    canvas.toolChanged.connect(_sync_lens_controls)
    canvas.scene.selectionChanged.connect(_sync_lens_controls)
    _sync_lens_controls()
    tb.addSeparator()

    add_action("new", "Новый снимок", window.new_screenshot, sc="Ctrl+N", icon=make_icon_new(), show_text=False)
    if hasattr(window, "request_series_capture"):
        add_action("series", "Серия скриншотов", window.request_series_capture, icon=make_icon_series(), show_text=False)
    if hasattr(window, "request_video_capture"):
        add_action("video", "Записать видео", window.request_video_capture, icon=make_icon_video(), show_text=False)
    add_action("collage", "История", window.open_collage, sc="Ctrl+K", icon=make_icon_collage(), show_text=False)
    add_action(
        "ocr",
        "Распознать текст",
        window.rerun_ocr_with_language,
        sc="Ctrl+Shift+O",
        icon=make_icon_ocr(),
        show_text=False,
    )
    add_action("copy", "Копировать", window.copy_to_clipboard, sc="Ctrl+C", icon=make_icon_copy(), show_text=False)
    add_action("save", "Сохранить", window.save_image, sc="Ctrl+S", icon=make_icon_save(), show_text=False)

    undo_act = canvas.undo_stack.createUndoAction(window, "Отмена")
    undo_act.setShortcut(QKeySequence("Ctrl+Z"))
    undo_act.setShortcutContext(Qt.ApplicationShortcut)
    redo_act = canvas.undo_stack.createRedoAction(window, "Повтор")
    redo_act.setShortcut(QKeySequence("Ctrl+Shift+Z"))
    redo_act.setShortcutContext(Qt.ApplicationShortcut)
    window.addAction(undo_act)
    window.addAction(redo_act)

    # Updated Undo/Redo buttons using icons
    btn_undo = QToolButton()
    btn_undo.setDefaultAction(undo_act)
    btn_undo.setIcon(make_icon_undo())
    btn_undo.setToolTip("Отменить (Ctrl+Z)")
    btn_undo.setToolButtonStyle(Qt.ToolButtonIconOnly)
    tb.addWidget(btn_undo)

    btn_redo = QToolButton()
    btn_redo.setDefaultAction(redo_act)
    btn_redo.setIcon(make_icon_redo())
    btn_redo.setToolTip("Повторить (Ctrl+Shift+Z)")
    btn_redo.setToolButtonStyle(Qt.ToolButtonIconOnly)
    tb.addWidget(btn_redo)

    # Контекстное меню для выбора формы скриншота
    def show_shape_menu(pos):
        new_button = buttons.get("new")
        if new_button is None:
            return
        menu = QMenu(new_button)
        rect_act = menu.addAction("Прямоугольник")
        circle_act = menu.addAction("Круг")
        chosen = menu.exec(new_button.mapToGlobal(pos))
        if chosen == rect_act:
            window.cfg["shape"] = "rect"
        elif chosen == circle_act:
            window.cfg["shape"] = "ellipse"
        save_config(window.cfg)

    new_btn = buttons.get("new")
    if new_btn is not None:
        new_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        new_btn.customContextMenuRequested.connect(show_shape_menu)

    # Применяем улучшенные стили
    tb.setStyleSheet(enhanced_actions_toolbar_style())

    return color_btn, actions, buttons
