"""Design tokens and shared UI styles for SlipSnap."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Palette:
    """Global color palette used across the application."""

    # Brand & primary colors
    PRIMARY: str = "#2563eb"
    PRIMARY_HOVER: str = "#1d4ed8"
    PRIMARY_LIGHT: str = "#dbeafe"

    # Neutral surfaces
    SURFACE: str = "#ffffff"
    SURFACE_ELEVATED: str = "#fafbfc"
    SURFACE_VARIANT: str = "#f8fafc"
    SURFACE_GRADIENT_END: str = "#f5f6f7"
    SURFACE_HOVER: str = "#f1f5f9"

    # Borders
    BORDER: str = "#e2e8f0"
    BORDER_ALT: str = "#d1d5db"
    BORDER_SOFT: str = "#e5e7eb"
    BORDER_FOCUS: str = "#3b82f6"

    # Typography
    TEXT_PRIMARY: str = "#0f172a"
    TEXT_SECONDARY: str = "#64748b"
    TEXT_MUTED: str = "#94a3b8"
    TEXT_INVERTED: str = "#f9fafb"
    TEXT_ACCENT: str = "#1e40af"
    TEXT_FOOTNOTE: str = "#6b7280"

    # Accents & status
    SUCCESS: str = "#10b981"
    WARNING: str = "#f59e0b"
    ERROR: str = "#ef4444"

    # Overlay / glassmorphism tokens
    OVERLAY_LABEL_BG: str = "rgba(30, 30, 35, 200)"
    OVERLAY_LABEL_BORDER: str = "rgba(255, 255, 255, 0.1)"
    OVERLAY_LABEL_TEXT: str = "#ffffff"
    OVERLAY_DRAW_PRIMARY: Tuple[int, int, int, int] = (70, 130, 240, 255)
    OVERLAY_DRAW_SECONDARY: Tuple[int, int, int, int] = (255, 255, 255, 180)
    TEXT_TOOL_COLOR: Tuple[int, int, int, int] = (255, 80, 80, 255)
    TEXT_TOOL_SELECTION: Tuple[int, int, int, int] = (70, 130, 240, 255)
    TEXT_TOOL_SELECTION_FILL: Tuple[int, int, int, int] = (255, 255, 255, 255)
    ERASER_MAIN_COLOR: Tuple[int, int, int, int] = (255, 100, 100, 120)
    ERASER_CENTER_COLOR: Tuple[int, int, int, int] = (255, 50, 50, 180)

    # Launcher widgets
    LAUNCHER_BG: str = "rgba(25, 25, 30, 240)"
    LAUNCHER_BORDER: str = "rgba(255, 255, 255, 0.08)"
    LAUNCHER_BUTTON_BG: str = "rgba(40, 40, 45, 120)"
    LAUNCHER_BUTTON_HOVER: str = "rgba(70, 130, 240, 200)"
    LAUNCHER_BUTTON_PRESSED: str = "rgba(60, 120, 220, 255)"
    LAUNCHER_BUTTON_TEXT: str = "#e5e7eb"

    # Shadow
    SHADOW_COLOR: Tuple[int, int, int, int] = (0, 0, 0, 80)

    # Icon accent colors for tray icons etc.
    ICON_BASE: Tuple[int, int, int] = (240, 240, 240)
    ICON_WARNING: Tuple[int, int, int] = (240, 80, 80)
    ICON_POSITIVE: Tuple[int, int, int] = (70, 130, 240)
    ICON_NEUTRAL: Tuple[int, int, int] = (120, 120, 120)
    ICON_SERIES_BACK: Tuple[int, int, int] = (180, 200, 255)
    ICON_SERIES_FRONT: Tuple[int, int, int] = (70, 130, 240)
    ICON_SERIES_COUNTER: Tuple[int, int, int] = (255, 255, 255)

    # Meme dialog palette
    MEME_BACKGROUND: str = "#ffffff"
    MEME_FOREGROUND: str = "#1a1a1a"
    MEME_LIST_BORDER: str = "#e5e5e5"
    MEME_LIST_BACKGROUND: str = "#fafafa"
    MEME_ITEM_BORDER: str = "#f0f0f0"
    MEME_ITEM_HOVER: str = "#f5f5f5"
    MEME_ITEM_SELECTED_BG: str = "#e3f2fd"
    MEME_ITEM_SELECTED_BORDER: str = "#2196f3"
    MEME_BUTTON_PRIMARY: str = "#2196f3"
    MEME_BUTTON_PRIMARY_HOVER: str = "#1976d2"
    MEME_BUTTON_PRIMARY_PRESSED: str = "#1565c0"
    MEME_BUTTON_DISABLED_BG: str = "#e0e0e0"
    MEME_BUTTON_DISABLED_TEXT: str = "#9e9e9e"
    MEME_BUTTON_REMOVE: str = "#f44336"
    MEME_BUTTON_REMOVE_HOVER: str = "#d32f2f"
    MEME_BUTTON_REMOVE_PRESSED: str = "#c62828"
    MEME_EMPTY_TEXT: str = "#757575"


@dataclass(frozen=True)
class Typography:
    """Font choices and sizes."""

    UI_FAMILY: str = "Montserrat"
    BASE_SIZE: int = 13
    SMALL_SIZE: int = 12
    BUTTON_SIZE: int = 16
    OVERLAY_HELP_SIZE: int = 13
    LAUNCHER_LABEL_SIZE: int = 14
    LAUNCHER_BUTTON_SIZE: int = 11
    TEXT_TOOL_DEFAULT_POINT: int = 18
    ABOUT_FOOTNOTE_SIZE: int = 11


@dataclass(frozen=True)
class Metrics:
    """Reusable sizing tokens for widgets."""

    MAIN_WINDOW_MIN_WIDTH: int = 680
    MAIN_WINDOW_MIN_HEIGHT: int = 540

    TOOL_BUTTON: int = 52
    TOOL_ICON: int = 40
    COLOR_BUTTON_WIDTH: int = 24
    COLOR_BUTTON_HEIGHT: int = 20
    COLOR_SWATCH: int = 24
    COLOR_BUTTON_RADIUS: int = 6
    COLOR_BUTTON_MIN_WIDTH: int = 20
    COLOR_BUTTON_MIN_HEIGHT: int = 16
    COLOR_DIALOG_PADDING: int = 8
    COLOR_DIALOG_SPACING: int = 4
    COLOR_SWATCH_RADIUS: int = 12
    ZOOM_SLIDER_WIDTH: int = 120

    ICON_SMALL: int = 28
    ICON_SHAPE: int = 24
    ICON_MARGIN_SMALL: int = 5
    ICON_MARGIN_MEDIUM: int = 7
    ICON_MARGIN_SERIES: int = 6
    ICON_SERIES_OFFSET: int = 4

    LAUNCHER_WIDTH: int = 260
    LAUNCHER_HEIGHT: int = 85
    LAUNCHER_ICON: int = 20
    LAUNCHER_MARGIN: Tuple[int, int, int, int] = (16, 12, 16, 14)
    LAUNCHER_SPACING: int = 10
    LAUNCHER_BUTTON_SPACING: int = 8
    LAUNCHER_SCREEN_TOP_OFFSET: int = 100

    OVERLAY_HINT_OFFSET: Tuple[int, int] = (24, 24)
    OVERLAY_HINT_SPACING: int = 12
    OVERLAY_SHADOW_BLUR: int = 20
    OVERLAY_SHADOW_OFFSET: Tuple[int, int] = (0, 6)

    MARKER_ALPHA: int = 80
    PENCIL_WIDTH: int = 3
    MARKER_WIDTH: int = 15

    MEME_DIALOG_MIN_WIDTH: int = 420
    MEME_DIALOG_MIN_HEIGHT: int = 480
    MEME_DIALOG_MARGIN: int = 16
    MEME_DIALOG_SPACING: int = 12
    MEME_LIST_ICON: int = 80
    MEME_LIST_GRID: Tuple[int, int] = (96, 106)
    MEME_LIST_SPACING: int = 8
    MEME_BUTTON_SIZE: int = 36
    MEME_EMPTY_PADDING: Tuple[int, int] = (30, 20)
    MEME_ITEM_EXTRA_SIZE: Tuple[int, int] = (16, 26)
    TEXT_RESIZE_HANDLE: int = 16
    ERASER_DEFAULT_SIZE: int = 20
    ERASER_MIN_SIZE: int = 5
    ERASER_MAX_SIZE: int = 100
    ERASER_STEP: int = 5


# Global stylesheet snippets -------------------------------------------------

def selection_overlay_label_style() -> str:
    """Shared label style for selection overlay hints."""

    return f"""
        QLabel {{
            color: {Palette.OVERLAY_LABEL_TEXT};
            background: {Palette.OVERLAY_LABEL_BG};
            padding: 12px 16px;
            font-size: {Typography.OVERLAY_HELP_SIZE}px;
            font-weight: 500;
            border-radius: 12px;
            border: 1px solid {Palette.OVERLAY_LABEL_BORDER};
        }}
    """


def launcher_container_style() -> str:
    """Glassmorphism inspired style for the tray launcher."""

    return f"""
        QWidget {{
            background: {Palette.LAUNCHER_BG};
            border-radius: 16px;
            border: 1px solid {Palette.LAUNCHER_BORDER};
        }}
        QToolButton {{
            background: {Palette.LAUNCHER_BUTTON_BG};
            border: none;
            border-radius: 12px;
            padding: 8px;
            color: {Palette.LAUNCHER_BUTTON_TEXT};
            font-weight: 500;
            font-size: {Typography.LAUNCHER_BUTTON_SIZE}px;
        }}
        QToolButton:hover {{
            background: {Palette.LAUNCHER_BUTTON_HOVER};
            color: {Palette.OVERLAY_LABEL_TEXT};
        }}
        QToolButton:pressed {{
            background: {Palette.LAUNCHER_BUTTON_PRESSED};
        }}
        QLabel {{
            color: {Palette.TEXT_INVERTED};
            font-size: {Typography.LAUNCHER_LABEL_SIZE}px;
            font-weight: 600;
        }}
    """


# Editor stylesheets ---------------------------------------------------------

def editor_main_stylesheet() -> str:
    """Full stylesheet for the editor main window."""

    return f"""
        QMainWindow {{
            background: #f8f9fa;
        }}

        QMenuBar {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {Palette.SURFACE},
                stop:1 {Palette.SURFACE_GRADIENT_END}
            );
            color: #1f2937;
            border: none;
            border-bottom: 1px solid {Palette.BORDER_SOFT};
            padding: 4px 8px;
            font-size: {Typography.BASE_SIZE}px;
            font-weight: 500;
        }}

        QMenuBar::item {{
            background: transparent;
            padding: 8px 16px;
            border-radius: 8px;
            margin: 2px;
            color: #374151;
        }}

        QMenuBar::item:selected {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #e0e7ff,
                stop:1 #dbeafe
            );
            color: {Palette.TEXT_ACCENT};
        }}

        QMenuBar::item:pressed {{
            background: #bfdbfe;
        }}

        QMenu {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER_ALT};
            border-radius: 12px;
            padding: 8px;
            color: #1f2937;
        }}

        QMenu::item {{
            padding: 10px 24px 10px 12px;
            border-radius: 8px;
            margin: 2px 4px;
            font-size: {Typography.BASE_SIZE}px;
            color: #374151;
        }}

        QMenu::item:selected {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #dbeafe,
                stop:1 #e0e7ff
            );
            color: {Palette.TEXT_ACCENT};
        }}

        QMenu::separator {{
            height: 1px;
            background: {Palette.BORDER_SOFT};
            margin: 6px 8px;
        }}

        QToolBar {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {Palette.SURFACE},
                stop:1 {Palette.SURFACE_ELEVATED}
            );
            border: none;
            border-bottom: 1px solid {Palette.BORDER_SOFT};
            spacing: 6px;
            padding: 10px 12px;
        }}

        QToolBar::separator {{
            width: 1px;
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(229, 231, 235, 0),
                stop:0.5 {Palette.BORDER_ALT},
                stop:1 rgba(229, 231, 235, 0)
            );
            margin: 6px 10px;
        }}

        QToolButton {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER_SOFT};
            border-radius: 10px;
            padding: 9px;
            color: #374151;
            font-weight: 500;
            min-width: 38px;
            min-height: 38px;
        }}

        QToolButton:hover {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #dbeafe,
                stop:1 #bfdbfe
            );
            border: 1px solid #93c5fd;
            color: {Palette.TEXT_ACCENT};
        }}

        QToolButton:pressed {{
            background: #bfdbfe;
            border: 1px solid #60a5fa;
            padding: 10px 8px 8px 10px;
        }}

        QToolButton:checked {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #dbeafe,
                stop:1 #bfdbfe
            );
            border: 1px solid #60a5fa;
            color: {Palette.TEXT_ACCENT};
            font-weight: 600;
        }}

        QToolButton:disabled {{
            background: #f3f4f6;
            border: 1px solid {Palette.BORDER_SOFT};
            color: #9ca3af;
        }}

        QStatusBar {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {Palette.SURFACE_ELEVATED},
                stop:1 #f3f4f6
            );
            color: #6b7280;
            border-top: 1px solid {Palette.BORDER_SOFT};
            padding: 6px 16px;
            font-size: {Typography.SMALL_SIZE}px;
            font-weight: 500;
        }}

        QStatusBar::item {{
            border: none;
        }}

        QMessageBox {{
            background: {Palette.SURFACE};
        }}

        QMessageBox QLabel {{
            color: #1f2937;
            font-size: {Typography.BASE_SIZE}px;
            padding: 8px;
        }}

        QMessageBox QPushButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #3b82f6,
                stop:1 {Palette.PRIMARY}
            );
            border: 1px solid {Palette.PRIMARY_HOVER};
            border-radius: 8px;
            padding: 10px 24px;
            color: white;
            font-weight: 600;
            min-width: 80px;
        }}

        QMessageBox QPushButton:hover {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #60a5fa,
                stop:1 #3b82f6
            );
        }}

        QMessageBox QPushButton:pressed {{
            background: {Palette.PRIMARY};
            padding: 11px 23px 9px 25px;
        }}

        QGraphicsView {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #f9fafb,
                stop:0.5 #f3f4f6,
                stop:1 #f9fafb
            );
            border: none;
        }}
    """


def overlay_hint_text() -> str:
    """Default text for the selection overlay helper."""

    return "ЛКМ — выделить  •  ⎵ — форма  •  Esc — отмена"


COLOR_SWATCHES = (
    "#1e293b",
    "#64748b",
    "#dc2626",
    "#ea580c",
    "#eab308",
    "#16a34a",
    "#0891b2",
    "#2563eb",
    "#7c3aed",
    "#ffffff",
)


def meme_dialog_stylesheet() -> str:
    """Stylesheet for the meme library dialog."""

    return f"""
        QWidget {{
            background: {Palette.MEME_BACKGROUND};
            color: {Palette.MEME_FOREGROUND};
        }}

        QListWidget {{
            border: 1px solid {Palette.MEME_LIST_BORDER};
            border-radius: 8px;
            padding: 12px;
            background: {Palette.MEME_LIST_BACKGROUND};
            outline: none;
        }}

        QListWidget::item {{
            border-radius: 8px;
            margin: 2px;
            padding: 6px;
            background: {Palette.MEME_BACKGROUND};
            border: 1px solid {Palette.MEME_ITEM_BORDER};
        }}

        QListWidget::item:hover {{
            background: {Palette.MEME_ITEM_HOVER};
            border: 1px solid {Palette.MEME_ITEM_BORDER};
        }}

        QListWidget::item:selected {{
            background: {Palette.MEME_ITEM_SELECTED_BG};
            border: 1px solid {Palette.MEME_ITEM_SELECTED_BORDER};
        }}

        QPushButton {{
            background: {Palette.MEME_BUTTON_PRIMARY};
            color: {Palette.OVERLAY_LABEL_TEXT};
            border: none;
            border-radius: 6px;
            font-size: {Typography.BUTTON_SIZE}px;
        }}

        QPushButton:hover {{
            background: {Palette.MEME_BUTTON_PRIMARY_HOVER};
        }}

        QPushButton:pressed {{
            background: {Palette.MEME_BUTTON_PRIMARY_PRESSED};
        }}

        QPushButton:disabled {{
            background: {Palette.MEME_BUTTON_DISABLED_BG};
            color: {Palette.MEME_BUTTON_DISABLED_TEXT};
        }}

        QPushButton#removeButton {{
            background: {Palette.MEME_BUTTON_REMOVE};
        }}

        QPushButton#removeButton:hover {{
            background: {Palette.MEME_BUTTON_REMOVE_HOVER};
        }}

        QPushButton#removeButton:pressed {{
            background: {Palette.MEME_BUTTON_REMOVE_PRESSED};
        }}

        QPushButton#removeButton:disabled {{
            background: {Palette.MEME_BUTTON_DISABLED_BG};
            color: {Palette.MEME_BUTTON_DISABLED_TEXT};
        }}

        QLabel#emptyLabel {{
            color: {Palette.MEME_EMPTY_TEXT};
            font-size: 14px;
            padding: {Metrics.MEME_EMPTY_PADDING[0]}px {Metrics.MEME_EMPTY_PADDING[1]}px;
        }}
    """
