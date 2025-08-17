from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QToolButton, QDialog, QGridLayout

from .styles import ModernColors


class ColorButton(QToolButton):
    """Small button showing selected color."""

    def __init__(self, color: QColor):
        super().__init__()
        self.color = color
        self.setFixedSize(24, 20)
        self.update_color()

    def update_color(self):
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {self.color.name()};
                border: 1px solid {ModernColors.BORDER};
                border-radius: 6px;
                min-width: 20px;
                min-height: 16px;
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
                border-radius: 12px;
                padding: 8px;
            }}
        """)

        colors = [
            "#1e293b", "#64748b", "#dc2626",
            "#ea580c", "#eab308", "#16a34a", "#0891b2",
            "#2563eb", "#7c3aed", "#ffffff"
        ]
        positions = [
            (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 1), (2, 2), (2, 3)
        ]

        layout = QGridLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        for pos, col in zip(positions, colors):
            btn = QToolButton()
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(f"""
                QToolButton{{
                    background: {col};
                    border: 2px solid {ModernColors.BORDER};
                    border-radius: 12px;
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
