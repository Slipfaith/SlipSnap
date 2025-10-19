from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap, QColor
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
    QGraphicsDropShadowEffect,
)

from meme_library import add_memes_from_paths, delete_memes, list_memes


class MemesDialog(QWidget):
    """Floating window that lets the user manage meme stickers."""

    memeSelected = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Мемы")
        self.setMinimumSize(360, 340)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._build_ui()
        self.refresh()

    # ---- UI helpers -------------------------------------------------
    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        glass = QWidget(self)
        glass.setObjectName("glassPanel")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(45)
        shadow.setOffset(0, 18)
        shadow.setColor(QColor(20, 56, 102, 90))
        glass.setGraphicsEffect(shadow)

        layout = QVBoxLayout(glass)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        root_layout.addWidget(glass)

        self._empty_label = QLabel("Добавьте свои мемы, чтобы быстро вставлять их в скриншоты.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setObjectName("emptyLabel")

        self._list = QListWidget(self)
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setFlow(QListView.LeftToRight)
        self._list.setWrapping(True)
        self._list.setIconSize(QSize(60, 60))
        self._list.setGridSize(QSize(70, 88))
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setUniformItemSizes(True)
        self._list.setMovement(QListWidget.Static)
        self._list.setSpacing(4)
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._list.setSelectionRectVisible(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)
        layout.addWidget(self._empty_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        add_btn = QPushButton("＋")
        add_btn.setObjectName("addButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setToolTip("Добавить мемы")
        add_btn.clicked.connect(self._add_memes)
        remove_btn = QPushButton("🗑️")
        remove_btn.setObjectName("removeButton")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setToolTip("Удалить выбранные мемы")
        remove_btn.clicked.connect(self._remove_selected)
        self._remove_btn = remove_btn

        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        layout.addLayout(buttons)
        self._list.itemSelectionChanged.connect(self._update_remove_state)
        self._update_remove_state()

        self.setStyleSheet(
            """
            #glassPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 160),
                    stop:1 rgba(190, 215, 255, 100));
                border-radius: 26px;
                border: 1px solid rgba(255, 255, 255, 180);
            }
            #glassPanel:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 190),
                    stop:1 rgba(210, 230, 255, 160));
            }
            QListWidget {
                border: 1px solid rgba(148, 163, 184, 120);
                border-radius: 18px;
                padding: 12px;
                background: rgba(255, 255, 255, 170);
            }
            QListWidget::item {
                border-radius: 18px;
                margin: 6px;
                padding: 6px;
                background: rgba(255, 255, 255, 60);
                border: 1px solid transparent;
            }
            QListWidget::item:hover {
                background: rgba(59, 130, 246, 90);
                border: 1px solid rgba(59, 130, 246, 140);
            }
            QListWidget::item:selected {
                border: 2px solid rgba(37, 99, 235, 180);
                background: rgba(37, 99, 235, 120);
            }
            QPushButton {
                background: rgba(59, 130, 246, 170);
                color: white;
                border: none;
                border-radius: 18px;
                padding: 10px 18px;
                font-size: 18px;
                font-weight: 600;
                min-width: 52px;
            }
            QPushButton:hover {
                background: rgba(37, 99, 235, 210);
                padding: 11px 20px;
            }
            QPushButton:disabled {
                background: rgba(148, 163, 184, 180);
                color: rgba(226, 232, 240, 200);
            }
            QPushButton#removeButton {
                background: rgba(239, 68, 68, 180);
            }
            QPushButton#removeButton:hover {
                background: rgba(220, 38, 38, 210);
            }
            QPushButton#removeButton:disabled {
                background: rgba(148, 163, 184, 180);
            }
            QLabel#emptyLabel {
                color: rgba(71, 85, 105, 220);
                font-size: 14px;
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
            scaled = pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            item = QListWidgetItem(QIcon(scaled), "")
            item.setSizeHint(QSize(70, 88))
            item.setData(Qt.UserRole, path)
            self._list.addItem(item)

        self._empty_label.setVisible(self._list.count() == 0)
        self._list.setVisible(self._list.count() > 0)
        self._update_remove_state()

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
            self.close()

    def _update_remove_state(self) -> None:
        has_selection = bool(self._list.selectedItems())
        self._remove_btn.setEnabled(has_selection)

    # ---- QWidget overrides -----------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

