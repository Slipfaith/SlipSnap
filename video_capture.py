from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from time import perf_counter, sleep
from typing import List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from design_tokens import Metrics, Palette, Typography, selection_overlay_label_style
from logic import save_config
from meme_gif_workflow import try_add_gif_to_meme_library
from video_encoding import MP4StreamEncoder, convert_mp4_to_gif


class _CaptureCanceled(Exception):
    """Internal control-flow exception for cancelled recording."""


class RegionSelectionOverlay(QWidget):
    region_selected = Signal(dict)
    canceled = Signal()

    def __init__(self, screen_map: List[Tuple[object, dict]]):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        primary = QGuiApplication.primaryScreen()
        if primary is None:
            raise RuntimeError("Не удалось определить основной экран для overlay.")
        virt = primary.virtualGeometry()
        self.setGeometry(virt)

        self._screen_map = screen_map
        self._done = False
        self._selecting = False
        self._origin = QPoint()
        self._current = QPoint()

        self._help = QLabel(self)
        self._help.setText("ЛКМ — область видео  •  Esc — отмена")
        self._help.setStyleSheet(selection_overlay_label_style())
        self._help.adjustSize()
        offset_x, offset_y = Metrics.OVERLAY_HINT_OFFSET
        self._help.move(offset_x, offset_y)

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._emit_canceled()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._selecting = True
            self._origin = event.globalPosition().toPoint()
            self._current = self._origin
            try:
                self.grabMouse()
            except Exception:
                pass
            self.update()

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._current = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._selecting:
            return
        self._selecting = False
        self._release_mouse_grab()
        self.update()
        selected = self._norm(self._origin, self._current)
        if selected.width() > 5 and selected.height() > 5:
            region = self._map_rect_to_phys(selected)
            if region["width"] > 0 and region["height"] > 0:
                self._emit_region(region)
                return
        self._emit_canceled()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._selecting:
            global_rect = self._norm(self._origin, self._current)
            local_rect = QRect(
                global_rect.x() - self.geometry().x(),
                global_rect.y() - self.geometry().y(),
                global_rect.width(),
                global_rect.height(),
            )
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(local_rect, Qt.transparent)
            painter.restore()

            primary = Palette.OVERLAY_DRAW_PRIMARY
            painter.setPen(QPen(QColor(*primary), 2, Qt.SolidLine))
            painter.drawRect(local_rect)

    def _norm(self, p1: QPoint, p2: QPoint) -> QRect:
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return QRect(left, top, right - left, bottom - top)

    def _release_mouse_grab(self) -> None:
        try:
            if QWidget.mouseGrabber() is self:
                self.releaseMouse()
        except Exception:
            pass

    @staticmethod
    def _nearest_screen(point: QPoint):
        screens = QGuiApplication.screens()
        if not screens:
            return QGuiApplication.primaryScreen()
        best = screens[0]
        best_dist = float("inf")
        px, py = point.x(), point.y()
        for screen in screens:
            g = screen.geometry()
            dx = 0
            if px < g.left():
                dx = g.left() - px
            elif px > g.right():
                dx = px - g.right()
            dy = 0
            if py < g.top():
                dy = g.top() - py
            elif py > g.bottom():
                dy = py - g.bottom()
            dist = float(dx * dx + dy * dy)
            if dist < best_dist:
                best = screen
                best_dist = dist
        return best

    def _screen_for_point(self, point: QPoint):
        screen = QGuiApplication.screenAt(point)
        if screen is not None:
            return screen
        nearest = self._nearest_screen(point)
        if nearest is not None:
            return nearest
        raise RuntimeError("Не удалось определить экран для координат выделения.")

    def _find_monitor(self, screen) -> dict:
        for sc, mon in self._screen_map:
            if sc is screen:
                return mon
        return self._screen_map[0][1]

    def _logical_to_phys(self, point: QPoint) -> Tuple[int, int]:
        screen = self._screen_for_point(point)
        monitor = self._find_monitor(screen)
        geom = screen.geometry()
        screen_w = max(1.0, float(geom.width()))
        screen_h = max(1.0, float(geom.height()))
        scale_x = float(monitor["width"]) / screen_w
        scale_y = float(monitor["height"]) / screen_h
        local_x = max(0.0, min(screen_w, float(point.x() - geom.x())))
        local_y = max(0.0, min(screen_h, float(point.y() - geom.y())))
        phys_x = int(round(float(monitor["left"]) + local_x * scale_x))
        phys_y = int(round(float(monitor["top"]) + local_y * scale_y))
        return phys_x, phys_y

    def _map_rect_to_phys(self, rect: QRect) -> dict:
        p1 = self._logical_to_phys(rect.topLeft())
        p2 = self._logical_to_phys(QPoint(rect.x() + rect.width(), rect.y() + rect.height()))
        left = min(p1[0], p2[0])
        top = min(p1[1], p2[1])
        right = max(p1[0], p2[0])
        bottom = max(p1[1], p2[1])
        return {
            "left": left,
            "top": top,
            "width": max(1, right - left),
            "height": max(1, bottom - top),
        }

    def _emit_region(self, region: dict) -> None:
        if self._done:
            return
        self._done = True
        self._release_mouse_grab()
        self.releaseKeyboard()
        self.close()
        self.region_selected.emit(region)

    def _emit_canceled(self) -> None:
        if self._done:
            return
        self._done = True
        self._release_mouse_grab()
        self.releaseKeyboard()
        self.canceled.emit()
        self.close()


class RecordingStatusWindow(QWidget):
    canceled = Signal()

    def __init__(self, total_frames: int):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self._total_frames = max(1, int(total_frames))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        panel = QWidget(self)
        panel.setObjectName("recordingPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(8)

        title = QLabel("Запись видео", panel)
        title.setObjectName("recordingTitle")
        self._status = QLabel("Осталось: -- сек", panel)
        self._status.setObjectName("recordingStatus")

        self._progress = QProgressBar(panel)
        self._progress.setRange(0, self._total_frames)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat(f"0/{self._total_frames} кадров")

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addStretch(1)
        cancel_btn = QPushButton("Отмена (Esc)", panel)
        cancel_btn.clicked.connect(self.canceled.emit)
        controls.addWidget(cancel_btn)

        panel_layout.addWidget(title)
        panel_layout.addWidget(self._status)
        panel_layout.addWidget(self._progress)
        panel_layout.addLayout(controls)
        root.addWidget(panel)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(Metrics.OVERLAY_SHADOW_BLUR)
        shadow_color = Palette.SHADOW_COLOR
        shadow.setColor(QColor(*shadow_color))
        offset_x, offset_y = Metrics.OVERLAY_SHADOW_OFFSET
        shadow.setOffset(offset_x, offset_y)
        panel.setGraphicsEffect(shadow)

        self.setStyleSheet(
            f"""
            QWidget#recordingPanel {{
                background: {Palette.LAUNCHER_BG};
                border-radius: 16px;
                border: 1px solid {Palette.LAUNCHER_BORDER};
            }}
            QLabel#recordingTitle {{
                color: {Palette.TEXT_INVERTED};
                font-size: {Typography.LAUNCHER_LABEL_SIZE}px;
                font-weight: 600;
            }}
            QLabel#recordingStatus {{
                color: {Palette.LAUNCHER_BUTTON_TEXT};
                font-size: {Typography.BASE_SIZE}px;
                font-weight: 500;
            }}
            QProgressBar {{
                background: rgba(40, 40, 45, 120);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                color: {Palette.TEXT_INVERTED};
                text-align: center;
                min-height: 16px;
                padding: 1px;
            }}
            QProgressBar::chunk {{
                border-radius: 7px;
                background: {Palette.PRIMARY};
            }}
            QPushButton {{
                background: {Palette.LAUNCHER_BUTTON_BG};
                border: none;
                border-radius: 10px;
                padding: 6px 12px;
                color: {Palette.LAUNCHER_BUTTON_TEXT};
                font-size: {Typography.SMALL_SIZE}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {Palette.LAUNCHER_BUTTON_HOVER};
                color: {Palette.OVERLAY_LABEL_TEXT};
            }}
            QPushButton:pressed {{
                background: {Palette.LAUNCHER_BUTTON_PRESSED};
            }}
            """
        )
        self.resize(360, 134)

    def showEvent(self, event):
        super().showEvent(event)
        self._reposition()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.canceled.emit()
            return
        super().keyPressEvent(event)

    def update_progress(self, captured: int, remaining_seconds: int) -> None:
        frame_no = max(0, min(self._total_frames, int(captured)))
        remaining = max(0, int(remaining_seconds))
        self._status.setText(f"Осталось: {remaining:02d} сек")
        self._progress.setValue(frame_no)
        self._progress.setFormat(f"{frame_no}/{self._total_frames} кадров")

    def _reposition(self) -> None:
        primary = QGuiApplication.primaryScreen()
        if primary is None:
            return
        geom = primary.availableGeometry()
        self.move(
            geom.center().x() - self.width() // 2,
            geom.top() + Metrics.LAUNCHER_SCREEN_TOP_OFFSET,
        )


class VideoSaveOptionsDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        base_dir: Path,
        default_name: str,
        default_format: str,
    ):
        super().__init__(parent)
        self.setWindowTitle("Сохранить видео")
        self.setModal(True)
        self.resize(560, 190)

        self._selected_path: Optional[Path] = None
        self._selected_format = "gif" if default_format == "gif" else "mp4"
        self._add_to_memes = False
        self._last_gif_checked = True

        layout = QVBoxLayout(self)
        form = QFormLayout()

        initial_path = Path(base_dir) / default_name
        self._path_edit = QLineEdit(str(initial_path), self)
        browse_btn = QPushButton("Обзор…", self)
        browse_btn.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)

        self._format_combo = QComboBox(self)
        self._format_combo.addItem("MP4", "mp4")
        self._format_combo.addItem("GIF", "gif")
        self._format_combo.setCurrentIndex(1 if self._selected_format == "gif" else 0)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)

        self._add_memes_checkbox = QCheckBox("Добавить в библиотеку мемов", self)
        self._add_memes_checkbox.setChecked(self._selected_format == "gif")

        form.addRow("Файл:", path_row)
        form.addRow("Формат:", self._format_combo)
        form.addRow("", self._add_memes_checkbox)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_format_changed()

    def _current_format(self) -> str:
        value = self._format_combo.currentData()
        return "gif" if value == "gif" else "mp4"

    @staticmethod
    def _normalize_path(path: Path, output_format: str) -> Path:
        ext = ".gif" if output_format == "gif" else ".mp4"
        if path.suffix.lower() == ext:
            return path
        return path.with_suffix(ext)

    def _on_format_changed(self) -> None:
        fmt = self._current_format()
        if fmt == "gif":
            self._add_memes_checkbox.setEnabled(True)
            self._add_memes_checkbox.setChecked(self._last_gif_checked)
        else:
            self._last_gif_checked = self._add_memes_checkbox.isChecked()
            self._add_memes_checkbox.setChecked(False)
            self._add_memes_checkbox.setEnabled(False)

    def _browse(self) -> None:
        current_text = self._path_edit.text().strip()
        start_path = current_text or str(Path.home() / f"clip.{self._current_format()}")
        default_filter = "GIF (*.gif)" if self._current_format() == "gif" else "MP4 (*.mp4)"
        selected_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Сохранить видео",
            start_path,
            "MP4 (*.mp4);;GIF (*.gif)",
            default_filter,
        )
        if not selected_path:
            return
        chosen_format = "gif" if "GIF" in selected_filter.upper() else "mp4"
        self._format_combo.setCurrentIndex(1 if chosen_format == "gif" else 0)
        normalized = self._normalize_path(Path(selected_path), chosen_format)
        self._path_edit.setText(str(normalized))

    def accept(self) -> None:
        raw = self._path_edit.text().strip().strip('"')
        if not raw:
            QMessageBox.warning(self, "SlipSnap", "Укажите путь для сохранения видео.")
            return
        try:
            path = Path(raw).expanduser()
        except Exception:
            QMessageBox.warning(self, "SlipSnap", "Некорректный путь для сохранения.")
            return

        output_format = self._current_format()
        self._selected_path = self._normalize_path(path, output_format)
        self._selected_format = output_format
        self._add_to_memes = output_format == "gif" and self._add_memes_checkbox.isChecked()
        super().accept()

    def selection(self) -> Tuple[Path, str, bool]:
        if self._selected_path is None:
            raise RuntimeError("Диалог сохранения не завершен успешно.")
        return self._selected_path, self._selected_format, self._add_to_memes


class VideoCaptureController(QObject):
    completed = Signal(str)
    canceled = Signal()
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        cfg: dict,
        grabber,
        ffmpeg_bin: str,
        parent_widget: Optional[QWidget] = None,
    ):
        super().__init__()
        self.cfg = cfg
        self._grabber = grabber
        self._ffmpeg_bin = ffmpeg_bin
        self._parent_widget = parent_widget
        self._overlay: Optional[RegionSelectionOverlay] = None
        self._cancel_requested = False
        self._active = False

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        try:
            mapping = self._match_monitors()
            if not mapping:
                raise RuntimeError("Не удалось сопоставить мониторы для выбора области.")
            self._overlay = RegionSelectionOverlay(mapping)
            self._overlay.region_selected.connect(self._on_region_selected)
            self._overlay.canceled.connect(self._on_overlay_canceled)
            self._overlay.show()
            self._overlay.raise_()
        except Exception as exc:
            self._active = False
            self.failed.emit(str(exc))
            self.finished.emit()

    def cancel_recording(self) -> None:
        self._cancel_requested = True

    def _on_overlay_canceled(self) -> None:
        self._overlay = None
        self._active = False
        self.canceled.emit()
        self.finished.emit()

    def _on_region_selected(self, region: dict) -> None:
        self._overlay = None
        try:
            output_path = self._record_and_save(region)
        except _CaptureCanceled:
            self._active = False
            self.canceled.emit()
            self.finished.emit()
            return
        except Exception as exc:
            self._active = False
            self.failed.emit(str(exc))
            self.finished.emit()
            return

        self._active = False
        self.completed.emit(str(output_path))
        self.finished.emit()

    def _duration_sec(self) -> int:
        raw = self.cfg.get("video_duration_sec", 6)
        try:
            value = int(raw)
        except Exception:
            value = 6
        return max(5, min(10, value))

    def _fps(self) -> int:
        raw = self.cfg.get("video_fps", 15)
        try:
            value = int(raw)
        except Exception:
            value = 15
        return max(10, min(24, value))

    def _record_and_save(self, region: dict) -> Path:
        duration = self._duration_sec()
        fps = self._fps()
        total_frames = max(1, int(round(duration * fps)))
        temp_mp4 = Path(tempfile.gettempdir()) / f"slipsnap_clip_{uuid4().hex}.mp4"

        encoder = MP4StreamEncoder(
            width=region["width"],
            height=region["height"],
            fps=fps,
            output_path=temp_mp4,
            ffmpeg_bin=self._ffmpeg_bin,
        )

        progress = RecordingStatusWindow(total_frames=total_frames)
        progress.canceled.connect(self.cancel_recording)
        progress.update_progress(captured=0, remaining_seconds=duration)
        progress.show()
        progress.raise_()

        self._cancel_requested = False
        captured = 0
        start_ts = perf_counter()
        next_frame_ts = start_ts

        try:
            while captured < total_frames:
                QApplication.processEvents()
                if self._cancel_requested:
                    raise _CaptureCanceled()

                now = perf_counter()
                if now < next_frame_ts:
                    sleep(min(next_frame_ts - now, 0.01))
                    continue

                shot = self._grabber._sct.grab(region)
                encoder.write_frame(shot.rgb)
                captured += 1
                next_frame_ts = start_ts + (captured / float(fps))

                elapsed = perf_counter() - start_ts
                remaining = max(0, int(round(duration - elapsed)))
                progress.update_progress(captured=captured, remaining_seconds=remaining)

            encoder.finalize()
            progress.update_progress(captured=total_frames, remaining_seconds=0)
        except _CaptureCanceled:
            encoder.abort()
            raise
        except Exception:
            encoder.abort()
            raise
        finally:
            progress.close()
            progress.deleteLater()

        try:
            target_path, output_format, add_to_memes = self._request_target_path()
            if target_path is None:
                raise _CaptureCanceled()

            target_path.parent.mkdir(parents=True, exist_ok=True)
            if output_format == "gif":
                convert_mp4_to_gif(
                    source_mp4=temp_mp4,
                    target_gif=target_path,
                    fps=min(12, fps),
                    ffmpeg_bin=self._ffmpeg_bin,
                )
            else:
                shutil.copy2(temp_mp4, target_path)

            self.cfg["video_default_format"] = output_format
            self.cfg["video_last_save_directory"] = str(target_path.parent)
            save_config(self.cfg)
            if output_format == "gif" and add_to_memes:
                result = try_add_gif_to_meme_library(target_path, stem=target_path.stem)
                if not result.ok:
                    QMessageBox.warning(
                        self._parent_widget,
                        "SlipSnap",
                        f"GIF сохранен, но не добавлен в библиотеку мемов:\n{result.error}",
                    )
            return target_path
        finally:
            try:
                temp_mp4.unlink(missing_ok=True)
            except Exception:
                pass

    def _request_target_path(self) -> Tuple[Optional[Path], str, bool]:
        default_format = str(self.cfg.get("video_default_format", "mp4")).lower()
        if default_format not in {"mp4", "gif"}:
            default_format = "mp4"

        base_dir = self._safe_output_dir(self.cfg.get("video_last_save_directory"))
        default_name = self._next_clip_filename(base_dir, default_format)
        dialog = VideoSaveOptionsDialog(
            parent=self._parent_widget,
            base_dir=base_dir,
            default_name=default_name,
            default_format=default_format,
        )
        if dialog.exec() != QDialog.Accepted:
            return None, default_format, False
        normalized_path, output_format, add_to_memes = dialog.selection()
        return normalized_path, output_format, add_to_memes

    @staticmethod
    def _safe_output_dir(value) -> Path:
        try:
            candidate = Path(str(value)).expanduser()
        except Exception:
            candidate = Path.home()
        if candidate.exists() and candidate.is_dir():
            return candidate
        return Path.home()

    @staticmethod
    def _next_clip_filename(base_dir: Path, extension: str) -> str:
        ext = "gif" if extension == "gif" else "mp4"
        for idx in range(1, 1000):
            name = f"clip_{idx:02d}.{ext}"
            if not (base_dir / name).exists():
                return name
        return f"clip.{ext}"

    def _match_monitors(self) -> List[Tuple[object, dict]]:
        try:
            return self._grabber.match_screens_to_monitors()
        except Exception:
            return []
