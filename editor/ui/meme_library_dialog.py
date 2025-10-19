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
    QVBoxLayout,
    QWidget,
)

from meme_library import add_memes_from_paths, delete_memes, list_memes


class MemesDialog(QWidget):
    """Минималистичное светлое окно для управления мемами"""

    memeSelected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Мемы")
        self.setMinimumSize(420, 480)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Мемы")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        self._empty_label = QLabel("Добавьте мемы для быстрой вставки")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setObjectName("emptyLabel")

        self._list = QListWidget(self)
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setFlow(QListView.LeftToRight)
        self._list.setWrapping(True)
        self._list.setIconSize(QSize(80, 80))
        self._list.setGridSize(QSize(96, 106))
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setUniformItemSizes(False)
        self._list.setMovement(QListWidget.Static)
        self._list.setSpacing(8)
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)

        add_btn = QPushButton("Добавить")
        add_btn.setObjectName("addButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_memes)

        remove_btn = QPushButton("Удалить")
        remove_btn.setObjectName("removeButton")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.clicked.connect(self._remove_selected)
        self._remove_btn = remove_btn

        buttons.addWidget(add_btn, 1)
        buttons.addWidget(remove_btn, 1)

        layout.addLayout(buttons)

        self._list.itemSelectionChanged.connect(self._update_remove_state)
        self._update_remove_state()

        self.setStyleSheet(
            """
            QWidget {
                background: #ffffff;
                color: #1a1a1a;
            }

            #titleLabel {
                color: #1a1a1a;
                font-size: 20px;
                font-weight: 600;
                padding-bottom: 4px;
            }

            QListWidget {
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 12px;
                background: #fafafa;
            }

            QListWidget::item {
                border-radius: 8px;
                margin: 2px;
                padding: 6px;
                background: #ffffff;
                border: 1px solid #f0f0f0;
            }

            QListWidget::item:hover {
                background: #f5f5f5;
                border: 1px solid #e0e0e0;
            }

            QListWidget::item:selected {
                background: #e3f2fd;
                border: 1px solid #2196f3;
            }

            QPushButton {
                background: #2196f3;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: 500;
            }

            QPushButton:hover {
                background: #1976d2;
            }

            QPushButton:pressed {
                background: #1565c0;
            }

            QPushButton:disabled {
                background: #e0e0e0;
                color: #9e9e9e;
            }

            QPushButton#removeButton {
                background: #f44336;
            }

            QPushButton#removeButton:hover {
                background: #d32f2f;
            }

            QPushButton#removeButton:pressed {
                background: #c62828;
            }

            QPushButton#removeButton:disabled {
                background: #e0e0e0;
                color: #9e9e9e;
            }

            QLabel#emptyLabel {
                color: #757575;
                font-size: 14px;
                padding: 30px 20px;
            }
            """
        )

    def refresh(self) -> None:
        self._list.clear()
        paths = list_memes()
        for path in paths:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                continue

            original_size = pixmap.size()
            max_dimension = 80

            if original_size.width() > original_size.height():
                new_width = max_dimension
                new_height = int(original_size.height() * max_dimension / original_size.width())
            else:
                new_height = max_dimension
                new_width = int(original_size.width() * max_dimension / original_size.height())

            scaled = pixmap.scaled(new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(QIcon(scaled), "")
            item.setSizeHint(QSize(new_width + 16, new_height + 26))
            item.setData(Qt.UserRole, path)
            self._list.addItem(item)

        self._empty_label.setVisible(self._list.count() == 0)
        self._list.setVisible(self._list.count() > 0)
        self._update_remove_state()

    def refresh_if_visible(self) -> None:
        if self.isVisible():
            self.refresh()

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
            self.close()

    def _update_remove_state(self) -> None:
        has_selection = bool(self._list.selectedItems())
        self._remove_btn.setEnabled(has_selection)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
