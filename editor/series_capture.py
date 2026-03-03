# -*- coding: utf-8 -*-
"""Tools for managing screenshot series workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

__all__ = ["SeriesCaptureController"]


@dataclass
class _SeriesSession:
    folder: Path
    prefix: str
    next_index: int
    saved_count: int = 0

    def ensure_ready(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)

    def next_path(self) -> Path:
        idx = self.next_index
        width = max(2, len(str(idx)))
        name = f"{self.prefix}{idx:0{width}d}.png"
        candidate = self.folder / name
        while candidate.exists():
            idx += 1
            width = max(2, len(str(idx)))
            name = f"{self.prefix}{idx:0{width}d}.png"
            candidate = self.folder / name
        self.next_index = idx
        return candidate

    def save(self, qimg: QImage) -> Path:
        if qimg.isNull():
            raise ValueError("Получено пустое изображение")
        self.ensure_ready()
        target = self.next_path()
        if not qimg.save(str(target), "PNG"):
            raise RuntimeError("Не удалось сохранить файл")
        self.saved_count += 1
        self.next_index += 1
        return target


class _SeriesSetupDialog(QDialog):
    """Dialog for configuring a screenshot series."""

    def __init__(self, parent: Optional[QWidget], prefix: str, folder: Path):
        super().__init__(parent)
        self.setWindowTitle("Серия скриншотов")
        self._folder = folder
        self._build_ui(prefix, folder)

    def _build_ui(self, prefix: str, folder: Path) -> None:
        layout = QGridLayout(self)
        layout.setColumnStretch(1, 1)

        info = QLabel(
            "Выберите папку и задайте имя серии. Скриншоты будут сохраняться"
            " автоматически без открытия редактора."
        )
        info.setWordWrap(True)
        layout.addWidget(info, 0, 0, 1, 2)

        name_label = QLabel("Имя серии:")
        layout.addWidget(name_label, 1, 0)

        self.name_edit = QLineEdit(prefix)
        layout.addWidget(self.name_edit, 1, 1)

        folder_label = QLabel("Папка сохранения:")
        layout.addWidget(folder_label, 2, 0)

        folder_row = QHBoxLayout()
        self.folder_display = QLineEdit(str(folder))
        self.folder_display.setReadOnly(True)
        folder_row.addWidget(self.folder_display)
        browse_btn = QPushButton("Выбрать…")
        browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row, 2, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons, 3, 0, 1, 2)

    def _on_browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Папка для серии", str(self._folder))
        if directory:
            self._folder = Path(directory)
            self.folder_display.setText(directory)

    def _on_accept(self) -> None:
        prefix = self.name_edit.text().strip()
        if not prefix:
            QMessageBox.warning(self, "SlipSnap", "Введите имя для серии.")
            return
        if not self._folder:
            QMessageBox.warning(self, "SlipSnap", "Выберите папку для сохранения.")
            return
        try:
            self._folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - filesystem errors
            QMessageBox.critical(
                self,
                "SlipSnap",
                f"Не удалось создать папку:\n{self._folder}\nОшибка: {exc}",
            )
            return
        self.accept()

    @property
    def folder(self) -> Path:
        return self._folder

    @property
    def prefix(self) -> str:
        return self.name_edit.text().strip()


class SeriesCaptureController:
    """High-level controller for screenshot series flow."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._session: Optional[_SeriesSession] = None
        self._last_capture = False

    # Public API ---------------------------------------------------------

    def is_active(self) -> bool:
        return self._session is not None

    def begin_session(self, parent: Optional[QWidget]) -> bool:
        if self._session:
            QMessageBox.information(
                parent,
                "SlipSnap",
                "Серия уже активна. Нажмите Esc в режиме съёмки, чтобы завершить её.",
            )
            return False

        default_prefix = self._cfg.get("series_prefix", "Series")
        default_folder = Path(self._cfg.get("series_folder", str(Path.home())))
        dlg = _SeriesSetupDialog(parent, default_prefix, default_folder)
        if dlg.exec() != QDialog.Accepted:
            return False

        prefix = dlg.prefix
        folder = dlg.folder
        start_index = self._resolve_initial_index(prefix, folder)
        self._session = _SeriesSession(folder=folder, prefix=prefix, next_index=start_index)
        self._last_capture = False
        self._cfg["series_prefix"] = prefix
        self._cfg["series_folder"] = str(folder)

        QMessageBox.information(
            parent,
            "SlipSnap",
            "Серия активирована. Используйте горячую клавишу съёмки для создания снимков.\n"
            "Нажмите Esc во время съёмки, чтобы завершить серию.",
        )
        return True

    def save_capture(self, parent: Optional[QWidget], qimg: QImage) -> Optional[Path]:
        if not self._session:
            return None
        try:
            path = self._session.save(qimg)
        except Exception as exc:  # pragma: no cover - depends on FS state
            QMessageBox.critical(
                parent,
                "SlipSnap",
                f"Не удалось сохранить скриншот серии:\n{exc}",
            )
            self._session = None
            self._last_capture = False
            return None
        else:
            self._last_capture = True
            return path

    def handle_overlay_finished(self, parent: Optional[QWidget]) -> bool:
        if not self._session:
            return False
        if self._last_capture:
            # Завершение после успешной записи кадра — серия активна
            self._last_capture = False
            return False

        saved = self._session.saved_count
        folder = self._session.folder
        self._session = None
        self._last_capture = False
        self._show_summary(parent, saved, folder)
        return True

    # Internal helpers --------------------------------------------------

    def _resolve_initial_index(self, prefix: str, folder: Path) -> int:
        pattern = re.compile(re.escape(prefix) + r"(\d+)\.png$", re.IGNORECASE)
        max_index = 0
        if folder.exists():
            for item in folder.iterdir():
                if not item.is_file():
                    continue
                match = pattern.match(item.name)
                if match:
                    try:
                        idx = int(match.group(1))
                    except ValueError:
                        continue
                    max_index = max(max_index, idx)
        return max_index + 1 if max_index else 1

    def _show_summary(self, parent: Optional[QWidget], saved: int, folder: Path) -> None:
        msg = QMessageBox(parent)
        msg.setWindowTitle("SlipSnap")
        msg.setIcon(QMessageBox.Information)
        msg.setText("Серия завершена")
        msg.setInformativeText(
            f"Создано скриншотов: {saved}\nПапка: {folder}"
        )
        open_btn = msg.addButton("Открыть папку", QMessageBox.ActionRole)
        ok_btn = msg.addButton(QMessageBox.Ok)
        msg.setDefaultButton(ok_btn)
        msg.exec()
        if msg.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))