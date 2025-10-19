from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QListView,
    QMessageBox,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from meme_library import add_memes_from_paths, delete_memes, list_memes


class MemeLibraryDialog(QWidget):
    """Floating window that lets the user manage meme stickers."""

    memeSelected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Библиотека мемов")
        self.setMinimumSize(340, 320)
        self._build_ui()
        self.refresh()

    # ---- UI helpers -------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._empty_label = QLabel("Добавьте свои мемы, чтобы быстро вставлять их в скриншоты.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setObjectName("emptyLabel")

        self._list = QListWidget(self)
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setFlow(QListView.LeftToRight)
        self._list.setWrapping(True)
        self._list.setIconSize(QSize(112, 112))
        self._list.setGridSize(QSize(136, 136))
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setUniformItemSizes(True)
        self._list.setMovement(QListWidget.Static)
        self._list.setSpacing(10)
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.setSelectionRectVisible(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        layout.addWidget(self._empty_label)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Добавить…")
        add_btn.clicked.connect(self._add_memes)
        remove_btn = QPushButton("Удалить выбранные")
        remove_btn.clicked.connect(self._remove_selected)
        close_btn = QPushButton("Закрыть")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.close)

        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        buttons.addWidget(close_btn)

        layout.addLayout(buttons)

        self.setStyleSheet(
            """
            QWidget {
                background: #f8f9fb;
            }
            QListWidget {
                border: 1px solid #d1d5db;
                border-radius: 14px;
                padding: 16px;
                background: #ffffff;
            }
            QListWidget::item {
                border-radius: 14px;
                margin: 4px;
                padding: 6px;
                background: transparent;
            }
            QListWidget::item:hover {
                background: rgba(37, 99, 235, 0.08);
            }
            QListWidget::item:selected {
                border: 2px solid #2563eb;
                background: rgba(37, 99, 235, 0.15);
            }
            QPushButton {
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
            QPushButton:disabled {
                background: #9ca3af;
                color: #e5e7eb;
            }
            QPushButton#closeButton {
                background: #6b7280;
            }
            QLabel#emptyLabel {
                color: #6b7280;
                font-size: 13px;
                padding: 24px 12px;
            }
            """
        )

    # ---- public API -------------------------------------------------
    def refresh(self) -> None:
        """Reload meme previews from disk."""

        self._list.clear()
        paths = list_memes()
        for path in paths:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                continue
            scaled = pixmap.scaled(112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(QIcon(scaled), "")
            item.setSizeHint(QSize(136, 136))
            item.setToolTip(path.name)
            item.setData(Qt.UserRole, path)
            self._list.addItem(item)

        self._empty_label.setVisible(self._list.count() == 0)
        self._list.setVisible(self._list.count() > 0)

    def refresh_if_visible(self) -> None:
        if self.isVisible():
            self.refresh()

    # ---- slots ------------------------------------------------------
    def _add_memes(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Добавить мемы",
            "",
            "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;Все файлы (*.*)",
        )
        if not files:
            return
        paths = [Path(f) for f in files]
        try:
            add_memes_from_paths(paths)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return
        self.refresh()

    def _remove_selected(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return
        paths = [item.data(Qt.UserRole) for item in items]
        delete_memes([p for p in paths if isinstance(p, Path)])
        self.refresh()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if isinstance(path, Path):
            self.memeSelected.emit(path)

    # ---- QWidget overrides -----------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

