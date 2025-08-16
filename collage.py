from typing import List
from pathlib import Path
from PIL import Image
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QCheckBox, QPushButton,
                               QLabel, QHBoxLayout, QSpinBox)
from logic import HISTORY_DIR, smart_grid

class CollageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Коллаж")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        self.grid = QGridLayout()
        layout.addLayout(self.grid)
        self.checks: List[QCheckBox] = []
        paths = sorted(HISTORY_DIR.glob("shot_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        for i, p in enumerate(paths):
            cb = QCheckBox(p.name)
            cb.setChecked(i < 4)
            self.checks.append(cb)
            btn = QPushButton("Просмотр")
            btn.clicked.connect(lambda _, pp=p: Image.open(pp).show())
            self.grid.addWidget(cb, i, 0)
            self.grid.addWidget(QLabel(str(p)), i, 1)
            self.grid.addWidget(btn, i, 2)

        h = QHBoxLayout()
        layout.addLayout(h)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(400, 8000)
        self.width_spin.setValue(1600)
        h.addWidget(QLabel("Ширина:"))
        h.addWidget(self.width_spin)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Создать")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        layout.addLayout(row)

    @property
    def target_width(self) -> int:
        return self.width_spin.value()

    def selected_images(self) -> List[Path]:
        out = []
        for i, cb in enumerate(self.checks):
            if cb.isChecked():
                out.append(Path(self.grid.itemAtPosition(i, 1).widget().text()))
        return out

def compose_collage(paths: List[Path], target_width: int) -> Image.Image:
    cols, rows = smart_grid(len(paths))
    aspect = 9/16
    target_height = int(target_width * aspect)
    cell_w = target_width // cols
    cell_h = target_height // rows
    canvas = Image.new("RGBA", (cell_w * cols, cell_h * rows), (30,30,30,255))
    i = 0
    for r in range(rows):
        for c in range(cols):
            if i >= len(paths):
                break
            im = Image.open(paths[i]).convert("RGBA")
            im.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
            x = c * cell_w + (cell_w - im.width)//2
            y = r * cell_h + (cell_h - im.height)//2
            canvas.paste(im, (x, y), im)
            i += 1
    return canvas