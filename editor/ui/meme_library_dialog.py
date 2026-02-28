from __future__ import annotations

from pathlib import Path
from typing import Dict

from PIL import Image
from PySide6.QtCore import QSize, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QIcon, QKeySequence, QMovie, QPainter, QPixmap, QShortcut, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from clipboard_utils import copy_gif_file_to_clipboard, copy_pil_image_to_clipboard
from design_tokens import Metrics, meme_dialog_stylesheet
from meme_library import add_memes_from_paths, delete_memes, list_memes
from logic import MEME_DIR, save_config


class MemesDialog(QWidget):
    """Dark modern meme library dialog with animated GIF previews."""

    memeSelected = Signal(Path)
    _THUMB_BATCH = 6
    _MAX_ANIMATED_VISIBLE = 12

    def __init__(self, parent=None, cfg: dict | None = None):
        super().__init__(parent, Qt.Window | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Библиотека мемов")
        self.setMinimumSize(Metrics.MEME_DIALOG_MIN_WIDTH, Metrics.MEME_DIALOG_MIN_HEIGHT)
        self._cfg = cfg
        self._gif_movies: Dict[Path, QMovie] = {}
        self._all_paths: list[Path] = []
        self._thumb_idx = 0
        self._size_save_timer = QTimer(self)
        self._size_save_timer.setSingleShot(True)
        self._size_save_timer.timeout.connect(self._persist_window_size)
        self._build_ui()
        self._restore_window_size()
        self.refresh()
        self._setup_shortcuts()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        margin = Metrics.MEME_DIALOG_MARGIN
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(Metrics.MEME_DIALOG_SPACING)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Мемы")
        title.setObjectName("titleLabel")
        subtitle = QLabel("Ctrl+C - копировать • Enter - вставить • Del - удалить")
        subtitle.setObjectName("subtitleLabel")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        self._stats_label = QLabel("0/0")
        self._stats_label.setObjectName("statsLabel")
        self._stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addLayout(title_block, 1)
        header.addWidget(self._stats_label)
        layout.addLayout(header)

        self._search_edit = QLineEdit(self)
        self._search_edit.setObjectName("searchEdit")
        self._search_edit.setPlaceholderText("Поиск по имени мема…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_edit)

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
        self._list.setFocusPolicy(Qt.StrongFocus)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.itemSelectionChanged.connect(self._update_action_state)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.verticalScrollBar().valueChanged.connect(self._sync_gif_playback)
        self._list.horizontalScrollBar().valueChanged.connect(self._sync_gif_playback)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(Metrics.MEME_LIST_SPACING)

        add_btn = QPushButton("Добавить")
        add_btn.setObjectName("addButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_memes)

        self._remove_btn = QPushButton("Удалить")
        self._remove_btn.setObjectName("removeButton")
        self._remove_btn.setCursor(Qt.PointingHandCursor)
        self._remove_btn.clicked.connect(self._remove_selected)

        self._open_folder_btn = QPushButton("Папка")
        self._open_folder_btn.setObjectName("openFolderButton")
        self._open_folder_btn.setCursor(Qt.PointingHandCursor)
        self._open_folder_btn.clicked.connect(self._open_meme_folder)

        self._insert_btn = QPushButton("Вставить")
        self._insert_btn.setObjectName("insertButton")
        self._insert_btn.setCursor(Qt.PointingHandCursor)
        self._insert_btn.clicked.connect(self._insert_selected)

        buttons.addWidget(add_btn)
        buttons.addWidget(self._remove_btn)
        buttons.addWidget(self._open_folder_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._insert_btn)
        layout.addLayout(buttons)

        self.setStyleSheet(meme_dialog_stylesheet())
        self._update_action_state()

    def _setup_shortcuts(self) -> None:
        self._copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self._copy_shortcut.activated.connect(self._copy_selected_to_clipboard)
        self._delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        self._delete_shortcut.activated.connect(self._remove_selected)
        self._rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self._rename_shortcut.activated.connect(self._rename_current_item)
        self._insert_shortcut = QShortcut(QKeySequence("Return"), self)
        self._insert_shortcut.activated.connect(self._insert_selected)
        self._insert_shortcut2 = QShortcut(QKeySequence("Enter"), self)
        self._insert_shortcut2.activated.connect(self._insert_selected)

    def refresh(self) -> None:
        self._all_paths = list_memes()
        self._reload_list()

    def _apply_filter(self, *_args) -> None:
        self._reload_list()

    def _reload_list(self) -> None:
        query = self._search_edit.text().strip().lower()
        if query:
            filtered = [p for p in self._all_paths if query in p.stem.lower() or query in p.name.lower()]
        else:
            filtered = list(self._all_paths)

        self._clear_gif_movies()
        self._list.clear()
        self._thumb_idx = 0

        extra_w, extra_h = Metrics.MEME_ITEM_EXTRA_SIZE
        icon_size = Metrics.MEME_LIST_ICON
        placeholder_size = QSize(icon_size + extra_w, icon_size + extra_h)

        for path in filtered:
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, path)
            item.setToolTip(path.name)
            item.setSizeHint(placeholder_size)
            self._list.addItem(item)

        total = len(self._all_paths)
        visible = len(filtered)
        self._stats_label.setText(f"{visible}/{total}")
        self._empty_label.setVisible(visible == 0)
        self._list.setVisible(visible > 0)
        self._update_action_state()

        if visible > 0:
            QTimer.singleShot(0, self._load_thumb_batch)

    def _release_gif_movie(self, path: Path) -> None:
        movie = self._gif_movies.pop(path, None)
        if movie is None:
            return
        try:
            movie.stop()
        except Exception:
            pass
        try:
            movie.setFileName("")
        except Exception:
            pass
        movie.deleteLater()

    def _clear_gif_movies(self) -> None:
        for path in list(self._gif_movies.keys()):
            self._release_gif_movie(path)

    @staticmethod
    def _scaled_preview_size(source_size: QSize, max_dimension: int) -> QSize:
        width = max(1, int(source_size.width()))
        height = max(1, int(source_size.height()))
        if width >= height:
            new_width = max_dimension
            new_height = max(1, int(round(height * max_dimension / float(width))))
        else:
            new_height = max_dimension
            new_width = max(1, int(round(width * max_dimension / float(height))))
        return QSize(new_width, new_height)

    @staticmethod
    def _with_badge(source: QPixmap, text: str) -> QPixmap:
        result = QPixmap(source)
        if result.isNull():
            return result

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing, True)
        badge_h = max(16, int(result.height() * 0.2))
        badge_w = max(34, int(result.width() * 0.42))
        x = max(0, result.width() - badge_w - 4)
        y = 4

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(16, 18, 24, 210))
        painter.drawRoundedRect(x, y, badge_w, badge_h, 6, 6)

        painter.setPen(QColor(235, 240, 255))
        painter.drawText(x, y, badge_w, badge_h, Qt.AlignCenter, text)
        painter.end()
        return result

    def _set_static_item_icon(
        self,
        item: QListWidgetItem,
        pixmap: QPixmap,
        max_dimension: int,
        badge_text: str | None = None,
    ) -> None:
        if pixmap.isNull():
            return
        extra_w, extra_h = Metrics.MEME_ITEM_EXTRA_SIZE
        target_size = self._scaled_preview_size(pixmap.size(), max_dimension)
        scaled = pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if badge_text:
            scaled = self._with_badge(scaled, badge_text)
        item.setIcon(QIcon(scaled))
        item.setSizeHint(QSize(target_size.width() + extra_w, target_size.height() + extra_h))

    def _set_broken_gif_icon(self, item: QListWidgetItem, max_dimension: int) -> None:
        base_size = max(48, int(max_dimension))
        preview = QPixmap(base_size, base_size)
        preview.fill(Qt.transparent)

        painter = QPainter(preview)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QColor(130, 140, 155))
        painter.setBrush(QColor(34, 39, 47))
        painter.drawRoundedRect(1, 1, base_size - 2, base_size - 2, 10, 10)
        painter.setPen(QColor(229, 233, 240))
        painter.drawText(preview.rect(), Qt.AlignCenter, "GIF\nERR")
        painter.end()

        self._set_static_item_icon(item, preview, max_dimension, badge_text="GIF")

    def _setup_gif_item(self, item: QListWidgetItem, path: Path, max_dimension: int) -> None:
        movie = QMovie(str(path))
        if not movie.isValid():
            fallback = QPixmap(str(path))
            if fallback.isNull():
                self._set_broken_gif_icon(item, max_dimension)
            else:
                self._set_static_item_icon(item, fallback, max_dimension, badge_text="GIF")
            return

        self._gif_movies[path] = movie

        def _on_frame_changed(_frame_no: int, target_item=item, target_movie=movie):
            pix = target_movie.currentPixmap()
            if pix.isNull():
                return
            self._set_static_item_icon(target_item, pix, max_dimension, badge_text="GIF")

        movie.frameChanged.connect(_on_frame_changed)
        movie.start()
        if movie.currentPixmap().isNull():
            movie.jumpToFrame(0)
        if movie.currentPixmap().isNull():
            self._set_broken_gif_icon(item, max_dimension)
        self._sync_gif_playback()

    def _load_thumb_batch(self) -> None:
        end = min(self._thumb_idx + self._THUMB_BATCH, self._list.count())
        max_dimension = Metrics.MEME_LIST_ICON

        for i in range(self._thumb_idx, end):
            item = self._list.item(i)
            if item is None:
                continue
            path = item.data(Qt.UserRole)
            if not isinstance(path, Path):
                continue

            if path.suffix.lower() == ".gif":
                self._setup_gif_item(item, path, max_dimension)
                continue

            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                continue
            self._set_static_item_icon(item, pixmap, max_dimension)

        self._thumb_idx = end
        if self._thumb_idx < self._list.count():
            QTimer.singleShot(0, self._load_thumb_batch)
        else:
            self._sync_gif_playback()

    def _sync_gif_playback(self, *_args) -> None:
        if not self._gif_movies:
            return
        visible_rect = self._list.viewport().rect()
        running = 0
        for idx in range(self._list.count()):
            item = self._list.item(idx)
            if item is None:
                continue
            path = item.data(Qt.UserRole)
            if not isinstance(path, Path) or path.suffix.lower() != ".gif":
                continue
            movie = self._gif_movies.get(path)
            if movie is None:
                continue
            item_rect = self._list.visualItemRect(item)
            visible = item_rect.isValid() and item_rect.intersects(visible_rect)
            should_run = visible and running < self._MAX_ANIMATED_VISIBLE and self.isVisible()
            if should_run:
                if movie.state() == QMovie.Paused:
                    movie.setPaused(False)
                elif movie.state() == QMovie.NotRunning:
                    movie.start()
                running += 1
            else:
                if movie.state() == QMovie.Running:
                    movie.setPaused(True)

    def _pause_all_gif_playback(self) -> None:
        for movie in self._gif_movies.values():
            if movie.state() == QMovie.Running:
                movie.setPaused(True)

    def refresh_if_visible(self) -> None:
        if self.isVisible():
            self.refresh()

    def _open_meme_folder(self) -> None:
        try:
            MEME_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(MEME_DIR)))
        if not opened:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку:\n{MEME_DIR}")

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
        paths = [item.data(Qt.UserRole) for item in items if isinstance(item.data(Qt.UserRole), Path)]
        if not paths:
            return

        count = len(paths)
        reply = QMessageBox.question(
            self,
            "Удаление мемов",
            f"Удалить выбранные элементы: {count}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for path in paths:
            self._release_gif_movie(path)
        QApplication.processEvents()
        delete_memes(paths)

        remaining = [p for p in paths if p.exists()]
        if remaining:
            self._clear_gif_movies()
            QApplication.processEvents()
            delete_memes(remaining)
            remaining = [p for p in remaining if p.exists()]
        if remaining:
            names = ", ".join(p.name for p in remaining[:4])
            if len(remaining) > 4:
                names += ", …"
            QMessageBox.warning(self, "Ошибка удаления", f"Не удалось удалить: {names}")
        self.refresh()

    def _copy_selected_to_clipboard(self) -> None:
        items = self._list.selectedItems()
        if not items:
            return

        path = items[0].data(Qt.UserRole)
        if not isinstance(path, Path):
            return

        if path.suffix.lower() == ".gif" and copy_gif_file_to_clipboard(path):
            return

        try:
            with Image.open(path) as img:
                copy_pil_image_to_clipboard(img)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось скопировать мем: {exc}")

    def _insert_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            selected = self._list.selectedItems()
            if not selected:
                return
            item = selected[0]
        self._on_item_double_clicked(item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if isinstance(path, Path):
            self.memeSelected.emit(path)
            self.close()

    def _show_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        menu = QMenu(self)
        insert_action = None
        copy_action = None
        rename_action = None
        delete_action = None

        if item is not None:
            insert_action = menu.addAction("Вставить")
            copy_action = menu.addAction("Копировать")
            rename_action = menu.addAction("Переименовать")
            delete_action = menu.addAction("Удалить")
            menu.addSeparator()
        open_folder_action = menu.addAction("Открыть папку мемов")

        chosen = menu.exec(self._list.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == open_folder_action:
            self._open_meme_folder()
            return
        if item is None:
            return
        if chosen == insert_action:
            self._on_item_double_clicked(item)
        elif chosen == copy_action:
            self._select_single_item(item)
            self._copy_selected_to_clipboard()
        elif chosen == rename_action:
            self._rename_item(item)
        elif chosen == delete_action:
            self._select_single_item(item)
            self._remove_selected()

    def _select_single_item(self, item: QListWidgetItem) -> None:
        self._list.clearSelection()
        item.setSelected(True)
        self._list.setCurrentItem(item)

    @staticmethod
    def _sanitize_rename_base(value: str) -> str:
        invalid = '<>:"/\\|?*'
        cleaned = "".join(ch for ch in value if ch not in invalid).strip().strip(".")
        if not cleaned:
            return ""
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        }
        if cleaned.upper() in reserved:
            return ""
        return cleaned

    @staticmethod
    def _unique_path(parent: Path, base: str, suffix: str) -> Path:
        candidate = parent / f"{base}{suffix}"
        idx = 1
        while candidate.exists():
            candidate = parent / f"{base}_{idx}{suffix}"
            idx += 1
        return candidate

    def _rename_current_item(self) -> None:
        item = self._list.currentItem()
        if item is None:
            selected = self._list.selectedItems()
            if not selected:
                return
            item = selected[0]
        self._rename_item(item)

    def _rename_item(self, item: QListWidgetItem) -> None:
        old_path = item.data(Qt.UserRole)
        if not isinstance(old_path, Path) or not old_path.exists():
            return
        current_name = old_path.stem
        new_name_raw, ok = QInputDialog.getText(
            self,
            "Переименовать мем",
            "Новое имя:",
            text=current_name,
        )
        if not ok:
            return
        new_base = self._sanitize_rename_base(Path(new_name_raw).stem)
        if not new_base:
            QMessageBox.warning(self, "Ошибка", "Введите корректное имя мема.")
            return
        if new_base == current_name:
            return

        target = old_path.with_name(f"{new_base}{old_path.suffix.lower()}")
        if target.exists():
            target = self._unique_path(old_path.parent, new_base, old_path.suffix.lower())

        self._release_gif_movie(old_path)
        QApplication.processEvents()
        try:
            old_path.rename(target)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось переименовать мем:\n{exc}")
            self.refresh()
            return
        self.refresh()

    def _update_action_state(self) -> None:
        has_selection = bool(self._list.selectedItems())
        self._remove_btn.setEnabled(has_selection)
        self._insert_btn.setEnabled(has_selection)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._size_save_timer.start(300)

    def _restore_window_size(self) -> None:
        if not isinstance(self._cfg, dict):
            return
        try:
            width = int(self._cfg.get("meme_dialog_width", Metrics.MEME_DIALOG_MIN_WIDTH))
            height = int(self._cfg.get("meme_dialog_height", Metrics.MEME_DIALOG_MIN_HEIGHT))
        except Exception:
            return
        width = max(Metrics.MEME_DIALOG_MIN_WIDTH, width)
        height = max(Metrics.MEME_DIALOG_MIN_HEIGHT, height)
        self.resize(width, height)

    def _persist_window_size(self) -> None:
        if not isinstance(self._cfg, dict):
            return
        self._cfg["meme_dialog_width"] = int(self.width())
        self._cfg["meme_dialog_height"] = int(self.height())
        try:
            save_config(self._cfg)
        except Exception:
            pass

    def hideEvent(self, event):
        self._persist_window_size()
        self._pause_all_gif_playback()
        super().hideEvent(event)
