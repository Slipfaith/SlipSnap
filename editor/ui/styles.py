class ModernColors:
    """Color palette used throughout the editor."""
    # Primary colors
    PRIMARY = "#2563eb"  # Modern blue
    PRIMARY_HOVER = "#1d4ed8"
    PRIMARY_LIGHT = "#dbeafe"

    # Surface colors
    SURFACE = "#ffffff"
    SURFACE_VARIANT = "#f8fafc"
    SURFACE_HOVER = "#f1f5f9"

    # Border colors
    BORDER = "#e2e8f0"
    BORDER_FOCUS = "#3b82f6"

    # Text colors
    TEXT_PRIMARY = "#0f172a"
    TEXT_SECONDARY = "#64748b"
    TEXT_MUTED = "#94a3b8"

    # Status colors
    SUCCESS = "#10b981"
    WARNING = "#f59e0b"
    ERROR = "#ef4444"


def main_window_style() -> str:
    """Return the global stylesheet for the editor window."""
    return f"""
    QMainWindow {{
        background: {ModernColors.SURFACE};
        color: {ModernColors.TEXT_PRIMARY};
    }}

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

    QToolButton {{
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

    QToolButton:hover {{
        background: {ModernColors.SURFACE_HOVER};
        color: {ModernColors.TEXT_PRIMARY};
        transform: translateY(-1px);
    }}

    QToolButton:pressed {{
        background: {ModernColors.PRIMARY_LIGHT};
        transform: translateY(0px);
    }}

    QToolButton:checked {{
        background: rgba(37, 99, 235, 0.2);
        color: white;
        border: 1px solid rgba(29, 78, 216, 0.4);
    }}

    QToolButton:checked:hover {{
        background: rgba(29, 78, 216, 0.3);
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

    QStatusBar {{
        background: {ModernColors.SURFACE_VARIANT};
        border-top: 1px solid {ModernColors.BORDER};
        color: {ModernColors.TEXT_SECONDARY};
        font-size: 12px;
        padding: 6px 16px;
    }}
    """


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
            stop:0 rgba(37, 99, 235, 0.2),
            stop:1 rgba(29, 78, 216, 0.3));
        border: 1px solid rgba(29, 78, 216, 0.4);
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
    }}
    QToolButton:hover {{
        background: {ModernColors.SURFACE_HOVER};
        transform: translateX(2px);
    }}
    QToolButton:checked:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(29, 78, 216, 0.3),
            stop:1 rgba(37, 99, 235, 0.2));
    }}
    QToolButton:pressed {{
        transform: scale(0.95);
    }}
    """
