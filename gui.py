from typing import List, Tuple, Optional, TYPE_CHECKING, Type
from pathlib import Path
from time import perf_counter
from PIL import Image, ImageQt
from PySide6.QtCore import (
    Qt,
    QRect,
    QRectF,
    QPoint,
    QSize,
    Signal,
    QObject,
    QAbstractNativeEventFilter,
    QAbstractEventDispatcher,
)
from PySide6.QtGui import (
    QGuiApplication,
    QPainter,
    QPen,
    QColor,
    QPixmap,
    QImage,
    QPainterPath,
    QIcon,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QToolButton,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QSpinBox,
    QSystemTrayIcon,
    QMenu,
)
from logic import load_config, save_config, qimage_to_pil, save_history
from clipboard_utils import copy_pil_image_to_clipboard
from icons import make_icon_capture, make_icon_shape, make_icon_close, make_icon_video
from pyqtkeybind import keybinder

from editor.series_capture import SeriesCaptureController
from ocr import configure_tesseract, warm_up_ocr
from video_capture import VideoCaptureController
from video_encoding import FFmpegUnavailableError, ensure_ffmpeg_available

from design_tokens import (
    Palette,
    Metrics,
    selection_overlay_label_style,
    launcher_container_style,
    overlay_hint_text,
)


if TYPE_CHECKING:
    from editor.editor_window import EditorWindow
    from logic import ScreenGrabber


class _KeybinderEventFilter(QAbstractNativeEventFilter):
    def nativeEventFilter(self, eventType, message):
        handled = keybinder.handler(eventType, message)
        return handled, 0


class SelectionOverlayBase(QWidget):
    captured = Signal(QImage)
    cancel_all = Signal()

    def __init__(self, base_img: Image.Image, cfg: dict, geom: QRect):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setGeometry(geom)

        self.cfg = cfg
        self.shape = cfg.get("shape", "rect")

        self.base_img = base_img.convert("RGBA")
        self._blur_factor = max(1, cfg.get("blur_radius", 2) * 2)
        self._bg_original = QPixmap.fromImage(ImageQt.ImageQt(self.base_img))
        self._bg_original_scaled = self._bg_original.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._bg_blurred_scaled = self._blur_pixmap(self._bg_original_scaled)

        self.origin = QPoint()
        self.current = QPoint()
        self.selecting = False

        self.help = QLabel(self)
        self.help.setText(overlay_hint_text())
        shared_style = selection_overlay_label_style()
        self.help.setStyleSheet(shared_style)
        self.help.adjustSize()
        offset_x, offset_y = Metrics.OVERLAY_HINT_OFFSET
        self.help.move(offset_x, offset_y)

        self.shape_hint = QLabel(self)
        self.shape_hint.setStyleSheet(shared_style)
        self.shape_hint.hide()
        self._update_shape_hint()

    def _blur_pixmap(self, pixmap: QPixmap) -> QPixmap:
        """Fast blur via downsample + upsample (no PIL dependency)."""
        w, h = pixmap.width(), pixmap.height()
        f = self._blur_factor
        if w < 2 or h < 2 or f < 2:
            return pixmap
        small = pixmap.scaled(
            max(1, w // f), max(1, h // f),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
        )
        return small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def set_shape(self, shape: str):
        self.shape = shape
        self._update_shape_hint()
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.activateWindow()
        self.raise_()
        self.grabKeyboard()

    def resizeEvent(self, e):
        self._bg_original_scaled = self._bg_original.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._bg_blurred_scaled = self._blur_pixmap(self._bg_original_scaled)
        super().resizeEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._release_mouse_grab()
            self.releaseKeyboard()
            self.cancel_all.emit()
            return
        if e.key() == Qt.Key_Space:
            self.shape = "ellipse" if self.shape == "rect" else "rect"
            self._update_shape_hint()
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.selecting = True
            self.origin = e.globalPosition().toPoint()
            self.current = self.origin
            try:
                self.grabMouse()
            except Exception:
                pass
            self._update_hint_visibility()
            self.update()

    def mouseMoveEvent(self, e):
        if self.selecting:
            self.current = e.globalPosition().toPoint()
            self._update_hint_visibility()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            self._release_mouse_grab()
            self._update_hint_visibility()
            gr = self._norm(self.origin, self.current)
            if gr.width() > 5 and gr.height() > 5:
                left, top, w, h = self._map_rect_to_image_coords(gr)
                if w > 0 and h > 0:
                    crop = self.base_img.crop((left, top, left + w, top + h))
                    mask = self._create_selection_mask(w, h)
                    result = crop.copy()
                    result.putalpha(mask)
                    qimg = copy_pil_image_to_clipboard(result)
                    self.captured.emit(qimg)
        self._release_mouse_grab()
        self.releaseKeyboard()
        self.cancel_all.emit()

    def _create_selection_mask(self, width: int, height: int) -> Image.Image:
        """Build a smooth alpha mask for the current selection shape.

        Uses Qt's native antialiased rendering instead of PIL super-sampling,
        avoiding large intermediate images (previously up to 8× the selection).
        """
        width = max(1, int(width))
        height = max(1, int(height))

        mask_img = QImage(width, height, QImage.Format_Grayscale8)
        mask_img.fill(0)

        p = QPainter(mask_img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))

        # Extend shape 1px beyond image bounds so straight edges are
        # fully opaque; only the rounded corners keep antialiased falloff.
        m = 1.0
        rect = QRectF(-m, -m, width + 2 * m, height + 2 * m)

        if self.shape == "ellipse":
            p.drawEllipse(rect)
        else:
            base_radius = max(4.0, min(width, height) * 0.04)
            p.drawRoundedRect(rect, base_radius, base_radius)

        p.end()

        # Convert QImage Grayscale8 → PIL "L"
        stride = mask_img.bytesPerLine()
        bits = bytes(mask_img.constBits())
        return Image.frombytes("L", (width, height), bits, "raw", "L", stride, 1)

    def _norm(self, p1: QPoint, p2: QPoint) -> QRect:
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        return QRect(left, top, right - left, bottom - top)

    def _release_mouse_grab(self) -> None:
        try:
            if QWidget.mouseGrabber() is self:
                self.releaseMouse()
        except Exception:
            pass

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(self.rect(), self._bg_blurred_scaled)

        if self.selecting:
            gr = self._norm(self.origin, self.current)
            loc = QRect(gr.x() - self.geometry().x(), gr.y() - self.geometry().y(), gr.width(), gr.height())

            if self.shape == "rect":
                path = QPainterPath()
                path.addRoundedRect(QRectF(loc), 12, 12)
                p.save()
                p.setClipPath(path)
                p.drawPixmap(loc, self._bg_original_scaled, loc)
                p.restore()
                p.setBrush(Qt.NoBrush)
                # Более стильная рамка
                primary = Palette.OVERLAY_DRAW_PRIMARY
                p.setPen(QPen(QColor(*primary), 3, Qt.SolidLine))
                p.drawPath(path)
            else:
                path = QPainterPath()
                path.addEllipse(QRectF(loc))
                p.save()
                p.setClipPath(path)
                p.drawPixmap(loc, self._bg_original_scaled, loc)
                p.restore()
                p.setBrush(Qt.NoBrush)
                # Более стильная рамка для эллипса
                primary = Palette.OVERLAY_DRAW_PRIMARY
                p.setPen(QPen(QColor(*primary), 3, Qt.SolidLine))
                p.drawEllipse(QRectF(loc))
        p.end()

    def _map_rect_to_image_coords(self, gr: QRect) -> Tuple[int, int, int, int]:
        raise NotImplementedError

    def _shape_display_name(self) -> str:
        return "Прямоугольник" if self.shape == "rect" else "Круг"

    def _update_shape_hint(self):
        text = f"Форма: {self._shape_display_name()}"
        self.shape_hint.setText(text)
        self.shape_hint.adjustSize()
        help_geo = self.help.geometry()
        spacing = Metrics.OVERLAY_HINT_SPACING
        self.shape_hint.move(help_geo.x(), help_geo.bottom() + spacing)
        self._update_hint_visibility()

    def _widget_global_rect(self, widget: QWidget) -> QRect:
        top_left = widget.mapToGlobal(QPoint(0, 0))
        return QRect(top_left, widget.size())

    def _update_hint_visibility(self):
        if not self.selecting:
            self.help.show()
            self.shape_hint.show()
            return

        selection_rect = self._norm(self.origin, self.current)
        overlaps_help = selection_rect.intersects(self._widget_global_rect(self.help))
        overlaps_shape = selection_rect.intersects(self._widget_global_rect(self.shape_hint))
        visible = not (overlaps_help or overlaps_shape)
        self.help.setVisible(visible)
        self.shape_hint.setVisible(visible)


class ScreenOverlay(SelectionOverlayBase):
    def __init__(self, screen, base_img: Image.Image, cfg: dict):
        super().__init__(base_img, cfg, screen.geometry())
        self._screen = screen

    def _map_rect_to_image_coords(self, gr: QRect) -> Tuple[int, int, int, int]:
        g = self._screen.geometry()
        screen_w = max(1.0, float(g.width()))
        screen_h = max(1.0, float(g.height()))
        img_w = float(max(1, self.base_img.width))
        img_h = float(max(1, self.base_img.height))
        scale_x = img_w / screen_w
        scale_y = img_h / screen_h
        lx = max(0.0, min(screen_w, float(gr.x() - g.x())))
        ly = max(0.0, min(screen_h, float(gr.y() - g.y())))
        left = int(round(lx * scale_x))
        top = int(round(ly * scale_y))
        w = int(round(float(gr.width()) * scale_x))
        h = int(round(float(gr.height()) * scale_y))
        return left, top, max(1, w), max(1, h)


class VirtualOverlay(SelectionOverlayBase):
    def __init__(
        self,
        base_img: Image.Image,
        cfg: dict,
        virt_geom: QRect,
        screen_map: List[Tuple[object, dict]],
        base_origin: Tuple[int, int],
    ):
        super().__init__(base_img, cfg, virt_geom)
        self._screen_map = screen_map
        self._base_left, self._base_top = base_origin

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

    def _screen_for_point(self, p: QPoint):
        s = QGuiApplication.screenAt(p)
        if s is not None:
            return s
        return self._nearest_screen(p)

    def _find_mon(self, screen) -> dict:
        for sc, mon in self._screen_map:
            if sc is screen:
                return mon
        return self._screen_map[0][1]

    def _logical_to_phys(self, p: QPoint) -> Tuple[int, int]:
        s = self._screen_for_point(p)
        if s is None:
            return 0, 0
        mon = self._find_mon(s)
        g = s.geometry()
        screen_w = max(1.0, float(g.width()))
        screen_h = max(1.0, float(g.height()))
        scale_x = float(mon["width"]) / screen_w
        scale_y = float(mon["height"]) / screen_h
        lx = max(0.0, min(screen_w, float(p.x() - g.x())))
        ly = max(0.0, min(screen_h, float(p.y() - g.y())))
        ax = int(round(float(mon["left"]) + lx * scale_x))
        ay = int(round(float(mon["top"]) + ly * scale_y))
        return ax - self._base_left, ay - self._base_top

    def _map_rect_to_image_coords(self, gr: QRect) -> Tuple[int, int, int, int]:
        p1 = self._logical_to_phys(gr.topLeft())
        p2 = self._logical_to_phys(QPoint(gr.x() + gr.width(), gr.y() + gr.height()))
        left = min(p1[0], p2[0])
        top = min(p1[1], p2[1])
        right = max(p1[0], p2[0])
        bottom = max(p1[1], p2[1])
        w = max(1, right - left)
        h = max(1, bottom - top)
        return left, top, w, h


class OverlayManager(QObject):
    captured = Signal(QImage)
    finished = Signal()

    def __init__(self, cfg: dict, grabber: Optional["ScreenGrabber"] = None):
        super().__init__()
        self.cfg = cfg
        self._grabber: Optional["ScreenGrabber"] = grabber
        self._overlays: List[SelectionOverlayBase] = []

    def _ensure_grabber(self) -> "ScreenGrabber":
        if self._grabber is None:
            from logic import ScreenGrabber

            self._grabber = ScreenGrabber()
        return self._grabber

    def _match_monitors(self) -> List[Tuple[object, dict]]:
        grabber = self._ensure_grabber()
        try:
            return grabber.match_screens_to_monitors()
        except Exception:
            return []

    def start(self):
        mode = self.cfg.get("capture_mode", "virtual")
        if mode == "per_screen":
            self._start_per_screen()
        else:
            self._start_virtual()

    def _start_virtual(self):
        primary = QGuiApplication.primaryScreen()
        if primary is None:
            raise RuntimeError("Не удалось определить основной экран.")
        virt = primary.virtualGeometry()
        grabber = self._ensure_grabber()
        img = grabber.grab_virtual()
        mapping = self._match_monitors()
        if not mapping:
            raise RuntimeError("Не удалось получить список физических мониторов MSS.")
        monitors = grabber._sct.monitors
        if not monitors:
            raise RuntimeError("Не удалось получить список мониторов MSS.")
        base_origin = (monitors[0]["left"], monitors[0]["top"])
        ov = VirtualOverlay(img, self.cfg, virt, mapping, base_origin)
        ov.captured.connect(self._on_captured)
        ov.cancel_all.connect(self.close_all)
        self._overlays = [ov]
        ov.show()
        ov.raise_()

    def _start_per_screen(self):
        mapping = self._match_monitors()
        if not mapping:
            raise RuntimeError("Не удалось получить список физических мониторов MSS.")
        grabber = self._ensure_grabber()
        for s, mon in mapping:
            img = grabber.grab(s)
            ov = ScreenOverlay(s, img, self.cfg)
            ov.captured.connect(self._on_captured)
            ov.cancel_all.connect(self.close_all)
            ov.showFullScreen()
            self._overlays.append(ov)

    def set_shape(self, shape: str):
        for ov in self._overlays:
            ov.set_shape(shape)

    def close_all(self):
        for ov in self._overlays:
            ov.close()
        self._overlays.clear()
        self.finished.emit()

    def _on_captured(self, qimg: QImage):
        self.captured.emit(qimg)


class Launcher(QWidget):
    start_capture = Signal()
    start_video = Signal()
    toggle_shape = Signal()
    hotkey_changed = Signal(str)
    request_hide = Signal()

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(Metrics.LAUNCHER_WIDTH, Metrics.LAUNCHER_HEIGHT)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        container = QWidget()
        container.setStyleSheet(launcher_container_style())

        layout = QVBoxLayout(container)
        left, top, right, bottom = Metrics.LAUNCHER_MARGIN
        layout.setContentsMargins(left, top, right, bottom)
        layout.setSpacing(Metrics.LAUNCHER_SPACING)

        title = QLabel("SlipSnap")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        btns = QHBoxLayout()
        btns.setSpacing(Metrics.LAUNCHER_BUTTON_SPACING)

        self.btn_capture = QToolButton()
        self.btn_capture.setIcon(make_icon_capture())
        self.btn_capture.setIconSize(QSize(Metrics.LAUNCHER_ICON, Metrics.LAUNCHER_ICON))
        self.btn_capture.setText("Снимок")
        self.btn_capture.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_capture.clicked.connect(self.start_capture.emit)
        btns.addWidget(self.btn_capture)

        self.btn_video = QToolButton()
        self.btn_video.setIcon(make_icon_video())
        self.btn_video.setIconSize(QSize(Metrics.LAUNCHER_ICON, Metrics.LAUNCHER_ICON))
        self.btn_video.setText("Видео")
        self.btn_video.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_video.clicked.connect(self.start_video.emit)
        btns.addWidget(self.btn_video)

        self.btn_shape = QToolButton()
        self.btn_shape.setIcon(make_icon_shape(self.cfg.get("shape", "rect")))
        self.btn_shape.setIconSize(QSize(Metrics.LAUNCHER_ICON, Metrics.LAUNCHER_ICON))
        self.btn_shape.setText("Круг" if self.cfg.get("shape", "rect") == "ellipse" else "Квадрат")
        self.btn_shape.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_shape.clicked.connect(self._on_shape)
        btns.addWidget(self.btn_shape)

        self.btn_hotkey = QToolButton()
        self.btn_hotkey.setText(self.cfg.get("capture_hotkey", "Ctrl+Alt+S"))
        self.btn_hotkey.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_hotkey.clicked.connect(self._on_hotkey)
        btns.addWidget(self.btn_hotkey)

        self.btn_close = QToolButton()
        self.btn_close.setIcon(make_icon_close())
        self.btn_close.setIconSize(QSize(Metrics.LAUNCHER_ICON, Metrics.LAUNCHER_ICON))
        self.btn_close.setText("Закрыть")
        self.btn_close.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_close.clicked.connect(self._on_close_clicked)
        btns.addWidget(self.btn_close)

        layout.addLayout(btns)
        main_layout.addWidget(container)

        self._drag_pos = None
        self._force_close_requested = False
        scr = QGuiApplication.primaryScreen().geometry()
        self.move(
            scr.center().x() - self.width() // 2,
            scr.top() + Metrics.LAUNCHER_SCREEN_TOP_OFFSET,
        )

        # Добавляем тень
        self.setGraphicsEffect(self._create_shadow_effect())

    def _on_close_clicked(self):
        self.request_hide.emit()

    def force_close(self):
        self._force_close_requested = True
        try:
            super().close()
        finally:
            self._force_close_requested = False

    def closeEvent(self, event):
        if self._force_close_requested:
            super().closeEvent(event)
            return
        event.ignore()
        self.request_hide.emit()

    def _create_shadow_effect(self):
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(Metrics.OVERLAY_SHADOW_BLUR)
        shadow_color = Palette.SHADOW_COLOR
        shadow.setColor(QColor(*shadow_color))
        offset_x, offset_y = Metrics.OVERLAY_SHADOW_OFFSET
        shadow.setOffset(offset_x, offset_y)
        return shadow

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def _on_shape(self):
        self.cfg["shape"] = "ellipse" if self.cfg.get("shape", "rect") == "rect" else "rect"
        save_config(self.cfg)
        self.btn_shape.setIcon(make_icon_shape(self.cfg["shape"]))
        self.btn_shape.setText("Круг" if self.cfg["shape"] == "ellipse" else "Квадрат")
        self.toggle_shape.emit()

    def _on_hotkey(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Настройки")
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        edit = QKeySequenceEdit(self.cfg.get("capture_hotkey", "Ctrl+Alt+S"))
        form.addRow("Горячая клавиша:", edit)

        try:
            duration_value = int(self.cfg.get("video_duration_sec", 6))
        except Exception:
            duration_value = 6
        duration_spin = QSpinBox(dlg)
        duration_spin.setRange(5, 10)
        duration_spin.setValue(max(5, min(10, duration_value)))
        form.addRow("Видео, сек:", duration_spin)

        try:
            fps_value = int(self.cfg.get("video_fps", 15))
        except Exception:
            fps_value = 15
        fps_spin = QSpinBox(dlg)
        fps_spin.setRange(10, 24)
        fps_spin.setValue(max(10, min(24, fps_value)))
        form.addRow("Видео FPS:", fps_spin)

        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec():
            seq = edit.keySequence().toString()
            if seq:
                self.cfg["capture_hotkey"] = seq
            self.cfg["video_duration_sec"] = duration_spin.value()
            self.cfg["video_fps"] = fps_spin.value()
            save_config(self.cfg)
            if seq:
                self.btn_hotkey.setText(seq)
                self.hotkey_changed.emit(seq)


class App(QObject):
    def __init__(self):
        super().__init__()
        init_started = perf_counter()
        self.cfg = load_config()
        configure_tesseract(self.cfg)
        warm_up_ocr()
        self.launcher = Launcher(self.cfg)
        self.launcher.start_capture.connect(self.capture_region)
        self.launcher.start_video.connect(self.capture_video)
        self.launcher.toggle_shape.connect(self._toggle_shape)
        self.launcher.hotkey_changed.connect(self._update_hotkey)
        self.launcher.request_hide.connect(self._on_launcher_hide_request)
        keybinder.init()
        dispatcher = QAbstractEventDispatcher.instance()
        self._keybinder_event_filter = None
        if dispatcher is not None:
            self._keybinder_event_filter = _KeybinderEventFilter()
            dispatcher.installNativeEventFilter(self._keybinder_event_filter)
        self._hotkey_seq = None
        self._register_hotkey(self.cfg.get("capture_hotkey", "Ctrl+Alt+S"))
        self.launcher.show()
        self._captured_once = False
        self._hidden_editors: List["EditorWindow"] = []
        self._capture_target_editor: Optional["EditorWindow"] = None
        self._full_capture_in_progress = False
        self._main_editor: Optional["EditorWindow"] = None
        self._screen_grabber: Optional["ScreenGrabber"] = None
        self._editor_window_cls: Optional[Type["EditorWindow"]] = None
        self._tray_icon: Optional[QSystemTrayIcon] = None
        self._tray_menu: Optional[QMenu] = None
        self._tray_action_capture = None
        self._tray_action_video = None
        self._tray_action_show = None
        self._tray_action_exit = None
        self._cleaned_up = False
        self._is_background = False
        self._video_capture_in_progress = False
        self._video_controller: Optional[VideoCaptureController] = None
        self._video_should_restore_launcher = False
        self._series_controller = SeriesCaptureController(self.cfg)
        self._series_parent: Optional[QWidget] = None
        self._init_tray_icon()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cleanup_on_exit)
        perf_counter() - init_started

    def _toggle_shape(self):
        if hasattr(self, "ovm"):
            self.ovm.set_shape(self.cfg.get("shape", "rect"))

    def _register_hotkey(self, seq: str, fallback_seq: Optional[str] = None):
        if self._hotkey_seq:
            try:
                # Passing ``None`` lets the backend decide which window handle
                # to use. Using ``0`` breaks registration on X11 backends
                # (pyqtkeybind expects ``None`` for the root window).
                keybinder.unregister_hotkey(None, self._hotkey_seq)
            except (KeyError, AttributeError):
                pass

        if keybinder.register_hotkey(None, seq, self.capture_region):
            self._hotkey_seq = seq
        else:
            self._hotkey_seq = None
            QMessageBox.warning(None, "SlipSnap", f"Не удалось зарегистрировать горячую клавишу: {seq}")
            if fallback_seq and fallback_seq != seq:
                if keybinder.register_hotkey(None, fallback_seq, self.capture_region):
                    self._hotkey_seq = fallback_seq
                    self.cfg["capture_hotkey"] = fallback_seq
                    save_config(self.cfg)
                    if hasattr(self.launcher, "btn_hotkey"):
                        self.launcher.btn_hotkey.setText(fallback_seq)

    def _update_hotkey(self, seq: str):
        self._register_hotkey(seq, fallback_seq=self._hotkey_seq)

    def _start_series_capture(self, parent: Optional[QWidget] = None) -> bool:
        if parent is None:
            parent = self.launcher
        if self._series_controller.begin_session(parent):
            save_config(self.cfg)
            self._series_parent = parent
            self._update_editor_series_buttons()
            return True
        if not self._series_controller.is_active():
            self._series_parent = None
        self._update_editor_series_buttons()
        return False

    def _start_video_capture(self, parent: Optional[QWidget] = None) -> bool:
        if self._video_capture_in_progress or self._full_capture_in_progress:
            return False
        self.capture_video(parent_widget=parent)
        return self._video_capture_in_progress

    def _on_series_captured(self, qimg: QImage):
        parent = self._series_parent or self.launcher
        result = self._series_controller.save_capture(parent, qimg)
        if result is None and not self._series_controller.is_active():
            self._series_parent = None
            self._update_editor_series_buttons()

    def _on_series_overlay_finished(self):
        parent = self._series_parent or self.launcher
        finished = self._series_controller.handle_overlay_finished(parent)
        if finished or not self._series_controller.is_active():
            self._restore_hidden_editors()
            self._series_parent = None
        self._update_editor_series_buttons()
        self._show_launcher()

    def _get_screen_grabber(self) -> "ScreenGrabber":
        if self._screen_grabber is None:
            from logic import ScreenGrabber

            self._screen_grabber = ScreenGrabber()
        return self._screen_grabber

    def _get_editor_window_class(self) -> Type["EditorWindow"]:
        if self._editor_window_cls is None:
            from editor.editor_window import EditorWindow

            self._editor_window_cls = EditorWindow
        return self._editor_window_cls

    def _editor_windows(self) -> List["EditorWindow"]:
        app = QApplication.instance()
        if app is None:
            return []
        EditorWindow = self._get_editor_window_class()
        return [w for w in app.topLevelWidgets() if isinstance(w, EditorWindow)]

    def _update_editor_series_buttons(self):
        for win in self._editor_windows():
            try:
                win.update_series_state()
            except Exception:
                continue

    def _hide_editor_windows(self):
        EditorWindow = self._get_editor_window_class()
        if self._series_controller.is_active():
            preserved: List["EditorWindow"] = []
            seen_ids = set()
            for win in self._hidden_editors:
                try:
                    win.isVisible()
                except RuntimeError:
                    continue
                identifier = id(win)
                if identifier in seen_ids:
                    continue
                preserved.append(win)
                seen_ids.add(identifier)
            self._hidden_editors = preserved
        else:
            self._hidden_editors = []
        self._capture_target_editor = None

        focus_window = QApplication.focusWindow()
        target: Optional["EditorWindow"] = None
        if isinstance(focus_window, EditorWindow):
            target = focus_window
        else:
            focus_widget = QApplication.focusWidget()
            if focus_widget is not None:
                try:
                    candidate = focus_widget.window()
                except Exception:
                    candidate = None
                if isinstance(candidate, EditorWindow):
                    target = candidate

        existing_ids = {id(win) for win in self._hidden_editors}

        for win in self._editor_windows():
            try:
                visible = win.isVisible()
            except RuntimeError:
                continue
            if not visible:
                continue
            try:
                win.begin_capture_hide()
            except Exception:
                continue
            identifier = id(win)
            if identifier not in existing_ids:
                self._hidden_editors.append(win)
                existing_ids.add(identifier)

        if target and target in self._hidden_editors:
            self._capture_target_editor = target

    def _restore_hidden_editors(self):
        for win in self._hidden_editors:
            try:
                win.restore_from_capture()
            except Exception:
                continue
        self._hidden_editors = []
        self._capture_target_editor = None

    def _on_launcher_hide_request(self):
        self._enter_background(from_user=True)

    def capture_region(self):
        if self._video_capture_in_progress:
            return
        self._hide_editor_windows()
        self.launcher.hide()
        try:
            self.ovm = OverlayManager(self.cfg, self._get_screen_grabber())
            if self._series_controller.is_active():
                self.ovm.captured.connect(self._on_series_captured)
                self.ovm.finished.connect(self._on_series_overlay_finished)
            else:
                self.ovm.captured.connect(self._on_captured)
                self.ovm.finished.connect(self._on_finished)
            self.ovm.start()
        except Exception as e:
            self.launcher.show()
            self._restore_hidden_editors()
            QMessageBox.critical(None, "SlipSnap", f"Ошибка съёмки: {e}")

    def capture(self):
        """Backward-compatible alias for region capture."""
        self.capture_region()

    def capture_video(self, _checked: bool = False, parent_widget: Optional[QWidget] = None):
        if self._video_capture_in_progress or self._full_capture_in_progress:
            return

        self._video_should_restore_launcher = not self._is_background and not self.launcher.isHidden()
        ffmpeg_bin = self._ensure_ffmpeg_ready()
        if not ffmpeg_bin:
            if self._video_should_restore_launcher:
                self._show_launcher()
            self._video_should_restore_launcher = False
            return

        self.launcher.hide()
        self._video_capture_in_progress = True
        self._update_tray_actions()

        try:
            self._video_controller = VideoCaptureController(
                self.cfg,
                self._get_screen_grabber(),
                ffmpeg_bin=ffmpeg_bin,
                parent_widget=parent_widget or self.launcher,
            )
            self._video_controller.completed.connect(self._on_video_completed)
            self._video_controller.failed.connect(self._on_video_failed)
            self._video_controller.canceled.connect(self._on_video_canceled)
            self._video_controller.finished.connect(self._on_video_finished)
            self._video_controller.start()
        except Exception as e:
            self._video_capture_in_progress = False
            self._update_tray_actions()
            self._video_controller = None
            if self._video_should_restore_launcher:
                self._show_launcher()
            self._video_should_restore_launcher = False
            QMessageBox.critical(None, "SlipSnap", f"Ошибка видео-захвата: {e}")

    def _ensure_ffmpeg_ready(self) -> Optional[str]:
        candidate_paths = []
        configured_path = str(self.cfg.get("ffmpeg_path", "")).strip()
        if configured_path:
            candidate_paths.append(configured_path)

        known_path = Path(r"C:\ffmpeg\bin\ffmpeg.exe")
        if known_path.exists():
            candidate_paths.append(str(known_path))
        candidate_paths.append(None)
        candidate_paths = list(dict.fromkeys(candidate_paths))

        while True:
            last_exc: Optional[FFmpegUnavailableError] = None
            for candidate in candidate_paths:
                try:
                    resolved = ensure_ffmpeg_available(candidate)
                    self.cfg["ffmpeg_path"] = resolved
                    save_config(self.cfg)
                    return resolved
                except FFmpegUnavailableError as exc:
                    last_exc = exc
                    continue

            if last_exc is not None:
                message = str(last_exc)
            else:
                message = "FFmpeg не найден. Установите ffmpeg и добавьте его в PATH."
            if known_path.exists():
                message += f"\n\nОбнаружен путь: {known_path}"
                message += "\nПриложение попробует использовать его автоматически."

            reply = QMessageBox.warning(
                None,
                "SlipSnap",
                f"{message}\n\n"
                "Для записи MP4/GIF установите ffmpeg и добавьте его в PATH.",
                QMessageBox.Retry | QMessageBox.Cancel,
                QMessageBox.Retry,
            )
            if reply != QMessageBox.Retry:
                return None

    def _on_video_completed(self, _output_path: str):
        self._captured_once = True

    def _on_video_failed(self, error_message: str):
        QMessageBox.critical(None, "SlipSnap", f"Ошибка видео-захвата: {error_message}")

    def _on_video_canceled(self):
        pass

    def _on_video_finished(self):
        self._video_capture_in_progress = False
        if self._video_controller is not None:
            try:
                self._video_controller.deleteLater()
            except Exception:
                pass
        self._video_controller = None
        if self._video_should_restore_launcher:
            self._show_launcher()
        self._video_should_restore_launcher = False
        self._update_tray_actions()

    def capture_fullscreen(self):
        if self._full_capture_in_progress or self._video_capture_in_progress:
            return

        self._full_capture_in_progress = True
        self._update_tray_actions()
        self._hide_editor_windows()
        self.launcher.hide()

        try:
            grabber = self._get_screen_grabber()
            img = grabber.grab_virtual()
        except Exception as e:
            self._full_capture_in_progress = False
            self._update_tray_actions()
            self.launcher.show()
            self._restore_hidden_editors()
            QMessageBox.critical(None, "SlipSnap", f"Ошибка съёмки: {e}")
            return

        try:
            qimg = copy_pil_image_to_clipboard(img)
        except Exception as e:
            self._full_capture_in_progress = False
            self._update_tray_actions()
            self.launcher.show()
            self._restore_hidden_editors()
            QMessageBox.critical(None, "SlipSnap", f"Ошибка обработки: {e}")
            return

        self._on_captured(qimg)
        self._restore_hidden_editors()
        self._full_capture_in_progress = False
        self._update_tray_actions()

    def _on_finished(self):
        self._restore_hidden_editors()
        if not self._captured_once:
            self._show_launcher()

    def _on_captured(self, qimg: QImage):
        try:
            img = qimage_to_pil(qimg)
            save_history(img)
            EditorWindow = self._get_editor_window_class()
            target_window: Optional["EditorWindow"] = None
            candidate = self._capture_target_editor
            if candidate and candidate in self._hidden_editors and hasattr(candidate, "load_base_screenshot"):
                try:
                    candidate.load_base_screenshot(qimg)
                    target_window = candidate
                except Exception:
                    target_window = None

            if target_window is None:
                existing: List["EditorWindow"] = []
                try:
                    existing = self._editor_windows()
                except Exception:
                    existing = []

                if self._main_editor and self._main_editor in existing:
                    try:
                        self._main_editor.load_base_screenshot(qimg)
                        target_window = self._main_editor
                    except Exception:
                        target_window = None

                if target_window is None and existing:
                    primary = existing[0]
                    try:
                        primary.load_base_screenshot(qimg)
                        target_window = primary
                    except Exception:
                        target_window = None

            if target_window is None:
                target_window = EditorWindow(qimg, self.cfg)
                target_window.destroyed.connect(self._on_main_editor_destroyed)
                self._main_editor = target_window
                target_window.show()
            else:
                if self._main_editor is None or self._main_editor is not target_window:
                    target_window.destroyed.connect(self._on_main_editor_destroyed)
                self._main_editor = target_window

            if hasattr(target_window, "set_series_controls"):
                try:
                    target_window.set_series_controls(
                        self._start_series_capture, self._series_controller.is_active
                    )
                except Exception:
                    pass
            if hasattr(target_window, "set_video_capture_controls"):
                try:
                    target_window.set_video_capture_controls(self._start_video_capture)
                except Exception:
                    pass

            try:
                target_window.showNormal()
                target_window.raise_()
                target_window.activateWindow()
            except Exception:
                pass

            self._capture_target_editor = None
            self._captured_once = True
            self._update_editor_series_buttons()
            self._enter_background()
        except Exception as e:
            QMessageBox.critical(None, "SlipSnap", f"Ошибка обработки: {e}")
            self.launcher.show()
            self._restore_hidden_editors()

    def _on_main_editor_destroyed(self, *_):
        self._main_editor = None

    def _init_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = self._resolve_tray_icon()
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setIcon(icon)
        self._tray_icon.setToolTip("SlipSnap")

        menu = QMenu("SlipSnap")
        title_action = menu.addAction("SlipSnap")
        title_action.setEnabled(False)
        menu.addSeparator()
        self._tray_action_show = menu.addAction("Открыть окно")
        self._tray_action_show.triggered.connect(self._show_launcher)
        self._tray_action_capture = menu.addAction("Сделать скриншот")
        self._tray_action_capture.triggered.connect(self.capture_region)
        self._tray_action_video = menu.addAction("Записать видео")
        self._tray_action_video.triggered.connect(self.capture_video)
        menu.addSeparator()
        self._tray_action_exit = menu.addAction("Выход")
        self._tray_action_exit.triggered.connect(self._exit_from_tray)

        self._tray_menu = menu
        self._tray_menu.aboutToShow.connect(self._on_tray_menu_about_to_show)
        self._tray_icon.setContextMenu(menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()
        self._update_tray_actions()

    def _on_tray_menu_about_to_show(self):
        if self._tray_menu is None:
            return
        self._tray_menu.setActiveAction(None)

    @staticmethod
    def _icon_has_visible_pixels(icon: QIcon) -> bool:
        if icon.isNull():
            return False

        for size in (16, 20, 24, 32):
            pm = icon.pixmap(size, size)
            if pm.isNull():
                continue
            img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
            raw = bytes(img.constBits())
            if any(raw[3::4]):
                return True
        return False

    def _build_fallback_tray_icon(self) -> QIcon:
        icon = QIcon()
        for size in (16, 20, 24, 32, 40):
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing, True)

            bg = QColor(26, 32, 44, 230)
            accent = QColor(88, 166, 255, 255)
            pad = 1 if size <= 20 else 2
            radius = max(3, int(round(size * 0.22)))

            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(pad, pad, size - 2 * pad, size - 2 * pad, radius, radius)

            pen_w = max(1, int(round(size * 0.1)))
            inner = max(3, int(round(size * 0.28)))
            span = max(1, size - 2 * inner)
            center = size // 2
            painter.setPen(QPen(accent, pen_w))
            painter.drawRect(inner, inner, span, span)
            painter.drawLine(center, inner + 1, center, size - inner - 1)
            painter.drawLine(inner + 1, center, size - inner - 1, center)
            painter.end()
            icon.addPixmap(pm)

        return icon

    def _resolve_tray_icon(self) -> QIcon:
        app = QApplication.instance()
        if app is not None and self._icon_has_visible_pixels(app.windowIcon()):
            return app.windowIcon()

        icon_path = Path(__file__).resolve().with_name("SlipSnap.ico")
        if icon_path.exists():
            file_icon = QIcon(str(icon_path))
            if self._icon_has_visible_pixels(file_icon):
                return file_icon

        fallback = self._build_fallback_tray_icon()
        if self._icon_has_visible_pixels(fallback):
            return fallback
        return make_icon_capture(40)

    def _show_launcher(self):
        if self.launcher.isHidden():
            self.launcher.show()
        try:
            self.launcher.raise_()
            self.launcher.activateWindow()
        except Exception:
            pass
        self._is_background = False
        self._update_tray_actions()

    def _enter_background(self, from_user: bool = False):
        if self._tray_icon is None:
            if from_user:
                self._exit_from_tray()
            else:
                self._show_launcher()
            return

        if not self.launcher.isHidden():
            self.launcher.hide()
        self._is_background = True
        self._release_background_resources()
        self._update_tray_actions()

    def _release_background_resources(self):
        self._hidden_editors = []
        self._capture_target_editor = None
        if self._main_editor is not None and not self._main_editor.isVisible():
            self._main_editor = None
        if getattr(self, "ovm", None) is not None:
            try:
                self.ovm.deleteLater()
            except Exception:
                pass
            self.ovm = None
        if self._video_controller is not None:
            try:
                self._video_controller.cancel_recording()
            except Exception:
                pass
            try:
                self._video_controller.deleteLater()
            except Exception:
                pass
            self._video_controller = None
            self._video_capture_in_progress = False
        self._video_should_restore_launcher = False
        self._screen_grabber = None
        self._editor_window_cls = None

    def _on_tray_activated(self, reason):
        if self._tray_menu is not None and self._tray_menu.isVisible():
            return
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self._is_background or self.launcher.isHidden():
                self._show_launcher()
            else:
                self._enter_background()

    def _exit_from_tray(self):
        if not self._cleanup_on_exit():
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _cleanup_on_exit(self):
        if self._cleaned_up:
            return True

        self._cleaned_up = True
        if self._hotkey_seq:
            try:
                keybinder.unregister_hotkey(None, self._hotkey_seq)
            except (KeyError, AttributeError):
                pass
            self._hotkey_seq = None

        if self._tray_icon is not None:
            self._tray_icon.hide()
            self._tray_icon.deleteLater()
            self._tray_icon = None

        if self._tray_menu is not None:
            self._tray_menu.deleteLater()
            self._tray_menu = None

        self._release_background_resources()
        try:
            self.launcher.force_close()
        except Exception:
            pass
        return True

    def _update_tray_actions(self):
        if self._tray_action_capture is not None:
            self._tray_action_capture.setEnabled(
                not self._full_capture_in_progress and not self._video_capture_in_progress
            )
        if self._tray_action_video is not None:
            self._tray_action_video.setEnabled(
                not self._full_capture_in_progress and not self._video_capture_in_progress
            )
