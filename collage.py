from typing import List, Tuple, Optional
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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


class PreviewDialog(QDialog):
    """Dialog that closes automatically when clicking outside of it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event_filter_installed = False

    def showEvent(self, event):
        super().showEvent(event)
        self._install_event_filter()

    def hideEvent(self, event):
        self._remove_event_filter()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._remove_event_filter()
        super().closeEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress and self.isVisible():
            if getattr(watched, "isWidgetType", lambda: False)():
                if watched is self or self.isAncestorOf(watched):
                    return False

            global_pos = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else event.globalPos()
            )
            if not self.rect().contains(self.mapFromGlobal(global_pos)):
                self._remove_event_filter()
                self.reject()
                return False

        return super().eventFilter(watched, event)

    def _install_event_filter(self) -> None:
        app = QApplication.instance()
        if app and not self._event_filter_installed:
            app.installEventFilter(self)
            self._event_filter_installed = True

    def _remove_event_filter(self) -> None:
        app = QApplication.instance()
        if app and self._event_filter_installed:
            app.removeEventFilter(self)
            self._event_filter_installed = False


class CollageDialog(QDialog):
    """Dialog to pick recent screenshots instead of creating a collage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История скриншотов")
        layout = QVBoxLayout(self)

        self.grid = QGridLayout()
        layout.addLayout(self.grid)

        self._buttons: List[Tuple[QToolButton, Path]] = []
        self._preview_dialog: Optional[PreviewDialog] = None

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
        if self._preview_dialog is not None:
            self._preview_dialog.close()

        dlg = PreviewDialog(self)
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
        dlg.finished.connect(self._on_preview_closed)
        self._preview_dialog = dlg
        dlg.show()

    def _on_preview_closed(self, _result: int) -> None:
        self._preview_dialog = None

