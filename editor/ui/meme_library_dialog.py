from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QSize, Signal, QTimer, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QGuiApplication, QImage, QPainterPath, QPen
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

from PIL import ImageFilter, ImageQt

from meme_library import add_memes_from_paths, delete_memes, list_memes


class BlurredPanel(QWidget):
    """Panel that mimics frosted glass by blurring what's behind it."""

    def __init__(
        self,
        parent=None,
        *,
        blur_radius: int = 24,
        radius: int = 22,
        tint: QColor | None = None,
        border_color: QColor | None = None,
    ):
        super().__init__(parent)
        self._blurred = QPixmap()
        self._update_pending = False
        self._blur_radius = blur_radius
        self._tint = tint or QColor(24, 28, 36, 180)
        self._radius = radius
        self._border_color = border_color or QColor(255, 255, 255, 35)

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_update()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), self._radius, self._radius)
        painter.setClipPath(path)

        if not self._blurred.isNull():
            painter.drawPixmap(rect, self._blurred)
        painter.fillPath(path, self._tint)
        painter.setClipPath(QPainterPath())
        if self._border_color.alpha() > 0:
            pen = QPen(self._border_color)
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.drawPath(path)
        painter.end()

    # ---- helpers -------------------------------------------------
    def _schedule_update(self):
        if self._update_pending:
            return
        self._update_pending = True
        QTimer.singleShot(0, self._update_background)

    def _update_background(self):
        self._update_pending = False
        rect = self.rect()
        if rect.isEmpty():
            return

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self._blurred = QPixmap()
            self.update()
            return

        top_left = self.mapToGlobal(rect.topLeft())
        grab = screen.grabWindow(0, top_left.x(), top_left.y(), rect.width(), rect.height())
        if grab.isNull():
            self._blurred = QPixmap()
            self.update()
            return

        qimage = grab.toImage().convertToFormat(QImage.Format_RGBA8888)
        pil_img = ImageQt.fromqimage(qimage)
        blurred = pil_img.filter(ImageFilter.GaussianBlur(self._blur_radius))
        qimg_blurred = ImageQt.ImageQt(blurred)
        self._blurred = QPixmap.fromImage(qimg_blurred)
        self.update()


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

        glass = BlurredPanel(self)
        glass.setObjectName("glassPanel")

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
                border-radius: 22px;
                border: 1px solid rgba(255, 255, 255, 35);
            }
            QListWidget {
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 16px;
                padding: 10px;
                background: rgba(18, 22, 30, 140);
                color: rgba(240, 244, 255, 220);
            }
            QListWidget::item {
                border-radius: 14px;
                margin: 4px;
                padding: 4px;
                background: rgba(255, 255, 255, 20);
                border: 1px solid transparent;
            }
            QListWidget::item:hover {
                background: rgba(96, 165, 250, 40);
                border: 1px solid rgba(148, 197, 255, 80);
            }
            QListWidget::item:selected {
                border: 1px solid rgba(129, 178, 255, 160);
                background: rgba(59, 130, 246, 90);
            }
            QPushButton {
                background: rgba(59, 130, 246, 160);
                color: rgba(244, 247, 255, 230);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 14px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: 600;
                min-width: 96px;
            }
            QPushButton:hover {
                background: rgba(37, 99, 235, 180);
            }
            QPushButton:disabled {
                background: rgba(71, 85, 105, 180);
                color: rgba(203, 213, 225, 160);
                border-color: rgba(255, 255, 255, 20);
            }
            QPushButton#removeButton {
                background: rgba(248, 113, 113, 160);
            }
            QPushButton#removeButton:hover {
                background: rgba(239, 68, 68, 180);
            }
            QPushButton#removeButton:disabled {
                background: rgba(71, 85, 105, 180);
            }
            QLabel#emptyLabel {
                color: rgba(226, 232, 240, 200);
                font-size: 13px;
                padding: 18px 8px;
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

