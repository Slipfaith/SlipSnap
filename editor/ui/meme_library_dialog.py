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

from design_tokens import Metrics, meme_dialog_stylesheet


class MemesDialog(QWidget):
    """Минималистичное светлое окно для управления мемами"""

    memeSelected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Мемы")
        self.setMinimumSize(Metrics.MEME_DIALOG_MIN_WIDTH, Metrics.MEME_DIALOG_MIN_HEIGHT)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        margin = Metrics.MEME_DIALOG_MARGIN
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(Metrics.MEME_DIALOG_SPACING)

        self._empty_label = QLabel("Добавьте мемы для быстрой вставки")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setObjectName("emptyLabel")

        self._list = QListWidget(self)
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setFlow(QListView.LeftToRight)
        self._list.setWrapping(True)
        self._list.setIconSize(QSize(Metrics.MEME_LIST_ICON, Metrics.MEME_LIST_ICON))
        grid_w, grid_h = Metrics.MEME_LIST_GRID
        self._list.setGridSize(QSize(grid_w, grid_h))
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setUniformItemSizes(False)
        self._list.setMovement(QListWidget.Static)
        self._list.setSpacing(Metrics.MEME_LIST_SPACING)
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(Metrics.MEME_LIST_SPACING)

        add_btn = QPushButton("➕")
        add_btn.setObjectName("addButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedSize(Metrics.MEME_BUTTON_SIZE, Metrics.MEME_BUTTON_SIZE)
        add_btn.setToolTip("Добавить мемы")
        add_btn.clicked.connect(self._add_memes)

        remove_btn = QPushButton("🗑️")
        remove_btn.setObjectName("removeButton")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setFixedSize(Metrics.MEME_BUTTON_SIZE, Metrics.MEME_BUTTON_SIZE)
        remove_btn.setToolTip("Удалить выбранные")
        remove_btn.clicked.connect(self._remove_selected)
        self._remove_btn = remove_btn

        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addStretch()

        layout.addLayout(buttons)

        self._list.itemSelectionChanged.connect(self._update_remove_state)
        self._update_remove_state()

        self.setStyleSheet(meme_dialog_stylesheet())

    def refresh(self) -> None:
        self._list.clear()
        paths = list_memes()
        for path in paths:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                continue

            original_size = pixmap.size()
            max_dimension = Metrics.MEME_LIST_ICON

            if original_size.width() > original_size.height():
                new_width = max_dimension
                new_height = int(original_size.height() * max_dimension / original_size.width())
            else:
                new_height = max_dimension
                new_width = int(original_size.width() * max_dimension / original_size.height())

            scaled = pixmap.scaled(new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(QIcon(scaled), "")
            extra_w, extra_h = Metrics.MEME_ITEM_EXTRA_SIZE
            item.setSizeHint(QSize(new_width + extra_w, new_height + extra_h))
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
