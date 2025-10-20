from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QToolButton, QDialog, QGridLayout

from .styles import ModernColors
from design_tokens import Metrics, COLOR_SWATCHES


class ColorButton(QToolButton):
    """Small button showing selected color."""

    def __init__(self, color: QColor):
        super().__init__()
        self.color = color
        self.setFixedSize(Metrics.COLOR_BUTTON_WIDTH, Metrics.COLOR_BUTTON_HEIGHT)
        self.update_color()

    def update_color(self):
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {self.color.name()};
                border: 1px solid {ModernColors.BORDER};
                border-radius: {Metrics.COLOR_BUTTON_RADIUS}px;
                min-width: {Metrics.COLOR_BUTTON_MIN_WIDTH}px;
                min-height: {Metrics.COLOR_BUTTON_MIN_HEIGHT}px;
            }}
            QToolButton:hover {{
                border: 2px solid {ModernColors.PRIMARY};
                transform: scale(1.05);
            }}
            QToolButton:pressed {{
                transform: scale(0.95);
            }}
        """)

    def set_color(self, color: QColor):
        self.color = color
        self.update_color()


class HexColorDialog(QDialog):
    """Hexagonal palette of colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup)
        self.selected = None
        self.setStyleSheet(f"""
            QDialog {{
                background: {ModernColors.SURFACE};
                border: 1px solid {ModernColors.BORDER};
                border-radius: {Metrics.COLOR_SWATCH_RADIUS}px;
                padding: {Metrics.COLOR_DIALOG_PADDING}px;
            }}
        """)

        colors = COLOR_SWATCHES
        positions = [
            (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 1), (2, 2), (2, 3)
        ]

        layout = QGridLayout(self)
        layout.setSpacing(Metrics.COLOR_DIALOG_SPACING)
        margin = Metrics.COLOR_DIALOG_PADDING
        layout.setContentsMargins(margin, margin, margin, margin)

        for pos, col in zip(positions, colors):
            btn = QToolButton()
            btn.setFixedSize(Metrics.COLOR_SWATCH, Metrics.COLOR_SWATCH)
            btn.setStyleSheet(f"""
                QToolButton{{
                    background: {col};
                    border: 2px solid {ModernColors.BORDER};
                    border-radius: {Metrics.COLOR_SWATCH_RADIUS}px;
                }}
                QToolButton:hover{{
                    border: 2px solid {ModernColors.PRIMARY};
                    transform: scale(1.1);
                }}
                QToolButton:pressed{{
                    transform: scale(0.9);
                }}
            """)
            btn.clicked.connect(lambda _=None, c=col: self._choose(c))
            layout.addWidget(btn, *pos)

    def _choose(self, color_str):
        self.selected = QColor(color_str)
        self.accept()
