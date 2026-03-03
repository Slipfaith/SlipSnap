# -*- coding: utf-8 -*-
from typing import List, Optional
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QEvent, QTimer, Signal
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
    """Превью скриншота. Закрывается кликом вне окна. Содержит кнопку «Добавить»."""

    added = Signal(Path)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = path
        self._event_filter_installed = False

        self.setWindowTitle(path.name)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(8)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        label = QLabel()
        pix = QPixmap(str(path))
        if not pix.isNull():
            label.setPixmap(pix)
            label.setAlignment(Qt.AlignCenter)
        scroll.setWidget(label)
        vbox.addWidget(scroll)

        row = QHBoxLayout()
        row.addStretch(1)
        add_btn = QPushButton("Добавить на холст")
        add_btn.setDefault(True)
        add_btn.clicked.connect(self._on_add)
        row.addWidget(add_btn)
        vbox.addLayout(row)

        if not pix.isNull():
            self.resize(
                min(pix.width() + 20, 800),
                min(pix.height() + 70, 660),
            )

    def _on_add(self) -> None:
        self._remove_event_filter()
        self.added.emit(self._path)
        self.accept()

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
    """История скриншотов.
    Одиночный клик — открывает превью с кнопкой «Добавить».
    Двойной клик — немедленно добавляет на холст.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История скриншотов")

        layout = QVBoxLayout(self)
        self.grid = QGridLayout()
        layout.addLayout(self.grid)

        self._buttons: List[tuple[QToolButton, Path]] = []
        self._preview_dialog: Optional[PreviewDialog] = None
        self._pending_paths: List[Path] = []

        # Таймер для разделения одиночного и двойного клика
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)
        self._click_pending_path: Optional[Path] = None
        self._click_timer.timeout.connect(self._open_pending_preview)

        paths = sorted(
            HISTORY_DIR.glob("shot_*.png"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]

        for i, p in enumerate(paths):
            btn = QToolButton()
            btn.setCheckable(False)
            pix = QPixmap(str(p))
            if not pix.isNull():
                btn.setIcon(
                    QIcon(pix.scaled(160, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                )
                btn.setIconSize(QSize(160, 90))
            btn.setToolTip(p.name)
            btn.clicked.connect(lambda checked=False, path=p: self._on_single_click(path))
            btn.installEventFilter(self)
            self._buttons.append((btn, p))
            self.grid.addWidget(btn, i // 5, i % 5)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonDblClick:
            for btn, path in self._buttons:
                if obj is btn:
                    self._click_timer.stop()
                    self._close_preview()
                    self._add_image(path)
                    return True
        return super().eventFilter(obj, event)

    def _on_single_click(self, path: Path) -> None:
        self._click_pending_path = path
        self._click_timer.start()

    def _open_pending_preview(self) -> None:
        if self._click_pending_path is not None:
            self._preview_image(self._click_pending_path)
            self._click_pending_path = None

    def selected_images(self) -> List[Path]:
        return list(self._pending_paths)

    def _add_image(self, path: Path) -> None:
        self._pending_paths = [path]
        self.accept()

    def _close_preview(self) -> None:
        if self._preview_dialog is not None:
            self._preview_dialog.close()
            self._preview_dialog = None

    def _preview_image(self, path: Path) -> None:
        self._close_preview()
        dlg = PreviewDialog(path, self)
        dlg.added.connect(self._add_image)
        dlg.finished.connect(self._on_preview_closed)
        self._preview_dialog = dlg
        dlg.show()

    def _on_preview_closed(self, _result: int) -> None:
        self._preview_dialog = None
