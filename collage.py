from typing import List, Tuple
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
)

from logic import HISTORY_DIR


class CollageDialog(QDialog):
    """Dialog to pick recent screenshots instead of creating a collage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История скриншотов")
        layout = QVBoxLayout(self)

        self.grid = QGridLayout()
        layout.addLayout(self.grid)

        self._buttons: List[Tuple[QToolButton, Path]] = []

        paths = sorted(
            HISTORY_DIR.glob("shot_*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]

        for i, p in enumerate(paths):
            btn = QToolButton()
            btn.setCheckable(True)
            pix = QPixmap(str(p))
            if not pix.isNull():
                btn.setIcon(
                    QIcon(
                        pix.scaled(
                            160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
                )
                btn.setIconSize(QSize(160, 90))
            btn.setToolTip(p.name)
            btn.clicked.connect(lambda checked=False, path=p: self._preview_image(path))
            self._buttons.append((btn, p))
            self.grid.addWidget(btn, i // 5, i % 5)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Добавить")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        layout.addLayout(row)

    def selected_images(self) -> List[Path]:
        out: List[Path] = []
        for btn, path in self._buttons:
            if btn.isChecked():
                out.append(path)
        return out

    def _preview_image(self, path: Path) -> None:
        """Open a simple dialog to preview the screenshot."""
        dlg = QDialog(self)
        dlg.setWindowTitle(path.name)
        vbox = QVBoxLayout(dlg)
        scroll = QScrollArea(dlg)
        label = QLabel()
        pix = QPixmap(str(path))
        if not pix.isNull():
            label.setPixmap(pix)
            label.setAlignment(Qt.AlignCenter)
        scroll.setWidget(label)
        vbox.addWidget(scroll)
        dlg.resize(min(pix.width() + 20, 800), min(pix.height() + 20, 600))
        dlg.exec()

