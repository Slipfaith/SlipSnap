from design_tokens import Palette, editor_main_stylesheet


class ModernColors:
    """Compatibility wrapper mapping to the global design palette."""

    # Primary colors
    PRIMARY = Palette.PRIMARY
    PRIMARY_HOVER = Palette.PRIMARY_HOVER
    PRIMARY_LIGHT = Palette.PRIMARY_LIGHT

    # Surface colors
    SURFACE = Palette.SURFACE
    SURFACE_VARIANT = Palette.SURFACE_VARIANT
    SURFACE_HOVER = Palette.SURFACE_HOVER

    # Border colors
    BORDER = Palette.BORDER
    BORDER_FOCUS = Palette.BORDER_FOCUS

    # Text colors
    TEXT_PRIMARY = Palette.TEXT_PRIMARY
    TEXT_SECONDARY = Palette.TEXT_SECONDARY
    TEXT_MUTED = Palette.TEXT_MUTED

    # Status colors
    SUCCESS = Palette.SUCCESS
    WARNING = Palette.WARNING
    ERROR = Palette.ERROR


def main_window_style() -> str:
    """Return the global stylesheet for the editor window."""

    return editor_main_stylesheet()


def tools_toolbar_style() -> str:
    """Return stylesheet for the vertical tools toolbar."""
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
    QToolButton {{
        background: transparent;
        border: none;
        border-radius: 12px;
        margin: 3px 0;
        padding: 6px;
    }}
    QToolButton:checked {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.PRIMARY_LIGHT},
            stop:1 {ModernColors.PRIMARY_LIGHT});
        border: 1px solid {ModernColors.PRIMARY_HOVER};
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
    }}
    QToolButton:hover {{
        background: {ModernColors.SURFACE_HOVER};
        transform: translateX(2px);
    }}
    QToolButton:checked:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ModernColors.PRIMARY_LIGHT},
            stop:1 {ModernColors.PRIMARY_LIGHT});
    }}
    QToolButton:pressed {{
        transform: scale(0.95);
    }}
    """
