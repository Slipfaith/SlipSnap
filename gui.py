from typing import List, Tuple
from PIL import Image, ImageFilter, ImageDraw, ImageQt
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QSize, Signal, QObject
from PySide6.QtGui import (
    QGuiApplication, QPainter, QPen, QColor, QPixmap, QImage, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QToolButton, QMessageBox
)

from logic import load_config, save_config, ScreenGrabber, qimage_to_pil, save_history
from editor import EditorWindow
from icons import make_icon_capture, make_icon_shape, make_icon_close


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
        blur_r = cfg.get("blur_radius", 8)
        self.blurred = self.base_img.filter(ImageFilter.GaussianBlur(radius=blur_r))
        self._bg_blurred = QPixmap.fromImage(ImageQt.ImageQt(self.blurred))
        self._bg_original = QPixmap.fromImage(ImageQt.ImageQt(self.base_img))
        self._bg_blurred_scaled = self._bg_blurred.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._bg_original_scaled = self._bg_original.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        self.origin = QPoint()
        self.current = QPoint()
        self.selecting = False

        self.help = QLabel(self)
        self.help.setText("ЛКМ — выделить  •  ⎵ — форма  •  Esc — отмена")
        self.help.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background: rgba(30, 30, 35, 200);
                padding: 12px 16px;
                font-size: 13px;
                font-weight: 500;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        self.help.adjustSize()
        self.help.move(24, 24)

    def set_shape(self, shape: str):
        self.shape = shape
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.activateWindow()
        self.raise_()
        self.grabKeyboard()

    def resizeEvent(self, e):
        self._bg_blurred_scaled = self._bg_blurred.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._bg_original_scaled = self._bg_original.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        super().resizeEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.releaseKeyboard()
            self.cancel_all.emit()
            return
        if e.key() == Qt.Key_Space:
            self.shape = "ellipse" if self.shape == "rect" else "rect"
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.selecting = True
            self.origin = e.globalPosition().toPoint()
            self.current = self.origin
            self.update()

    def mouseMoveEvent(self, e):
        if self.selecting:
            self.current = e.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            gr = self._norm(self.origin, self.current)
            if gr.width() > 5 and gr.height() > 5:
                left, top, w, h = self._map_rect_to_image_coords(gr)
                crop = self.base_img.crop((left, top, left + w, top + h))
                if self.shape == "ellipse":
                    mask = Image.new("L", (w, h), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, w, h), fill=255)
                    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    out.paste(crop, (0, 0), mask)
                    crop = out
                self.captured.emit(ImageQt.ImageQt(crop))
        self.releaseKeyboard()
        self.cancel_all.emit()

    def _norm(self, p1: QPoint, p2: QPoint) -> QRect:
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        left, right = sorted([x1, x2])
        top, bottom = sorted([y1, y2])
        return QRect(left, top, right - left, bottom - top)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(self.rect(), self._bg_blurred_scaled)

        if self.selecting:
            gr = self._norm(self.origin, self.current)
            loc = QRect(gr.x() - self.geometry().x(), gr.y() - self.geometry().y(), gr.width(), gr.height())

            if self.shape == "rect":
                p.drawPixmap(loc, self._bg_original_scaled, loc)
                # Более стильная рамка
                p.setPen(QPen(QColor(70, 130, 240), 3, Qt.SolidLine))
                p.drawRect(loc)
                # Внутренняя светлая рамка
                p.setPen(QPen(QColor(255, 255, 255, 180), 1, Qt.SolidLine))
                inner_rect = QRect(loc.x() + 1, loc.y() + 1, loc.width() - 2, loc.height() - 2)
                p.drawRect(inner_rect)
            else:
                path = QPainterPath()
                path.addEllipse(QRectF(loc))
                p.save()
                p.setClipPath(path)
                p.drawPixmap(loc, self._bg_original_scaled, loc)
                p.restore()
                p.setBrush(Qt.NoBrush)
                # Более стильная рамка для эллипса
                p.setPen(QPen(QColor(70, 130, 240), 3, Qt.SolidLine))
                p.drawEllipse(QRectF(loc))
                # Внутренняя светлая рамка
                p.setPen(QPen(QColor(255, 255, 255, 180), 1, Qt.SolidLine))
                inner_ellipse = QRectF(loc.x() + 1, loc.y() + 1, loc.width() - 2, loc.height() - 2)
                p.drawEllipse(inner_ellipse)
        p.end()

    def _map_rect_to_image_coords(self, gr: QRect) -> Tuple[int, int, int, int]:
        raise NotImplementedError


class ScreenOverlay(SelectionOverlayBase):
    def __init__(self, screen, base_img: Image.Image, cfg: dict):
        super().__init__(base_img, cfg, screen.geometry())
        self._screen = screen

    def _map_rect_to_image_coords(self, gr: QRect) -> Tuple[int, int, int, int]:
        g = self._screen.geometry()
        try:
            dpr = float(self._screen.devicePixelRatio())
        except Exception:
            dpr = 1.0
        lx = gr.x() - g.x()
        ly = gr.y() - g.y()
        left = int(round(lx * dpr))
        top = int(round(ly * dpr))
        w = int(round(gr.width() * dpr))
        h = int(round(gr.height() * dpr))
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

    def _screen_for_point(self, p: QPoint):
        s = QGuiApplication.screenAt(p)
        return s if s else QGuiApplication.primaryScreen()

    def _find_mon(self, screen) -> dict:
        for sc, mon in self._screen_map:
            if sc is screen:
                return mon
        return self._screen_map[0][1]

    def _logical_to_phys(self, p: QPoint) -> Tuple[int, int]:
        s = self._screen_for_point(p)
        mon = self._find_mon(s)
        g = s.geometry()
        try:
            dpr = float(s.devicePixelRatio())
        except Exception:
            dpr = 1.0
        lx = p.x() - g.x()
        ly = p.y() - g.y()
        ax = mon["left"] + int(round(lx * dpr))
        ay = mon["top"] + int(round(ly * dpr))
        return ax - self._base_left, ay - self._base_top

    def _map_rect_to_image_coords(self, gr: QRect) -> Tuple[int, int, int, int]:
        p1 = self._logical_to_phys(gr.topLeft())
        p2 = self._logical_to_phys(gr.bottomRight())
        left = min(p1[0], p2[0])
        top = min(p1[1], p2[1])
        right = max(p1[0], p2[0])
        bottom = max(p1[1], p2[1])
        w = max(1, right - left)
        h = max(1, bottom - top)
        return left, top, w, h


class OverlayManager(QObject):
    captured = Signal(QImage)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._grabber = ScreenGrabber()
        self._overlays: List[SelectionOverlayBase] = []

    def _screen_phys_rect(self, s) -> Tuple[int, int, int, int]:
        g = s.geometry()
        try:
            dpr = float(s.devicePixelRatio())
        except Exception:
            dpr = 1.0
        return (
            int(round(g.x() * dpr)),
            int(round(g.y() * dpr)),
            int(round(g.width() * dpr)),
            int(round(g.height() * dpr)),
        )

    def _match_monitors(self) -> List[Tuple[object, dict]]:
        sct = self._grabber._sct
        mons = sct.monitors[1:]
        out: List[Tuple[object, dict]] = []
        for s in QGuiApplication.screens():
            sx, sy, sw, sh = self._screen_phys_rect(s)
            exact = None
            for m in mons:
                if m["left"] == sx and m["top"] == sy and m["width"] == sw and m["height"] == sh:
                    exact = m
                    break
            if exact:
                out.append((s, exact))
                continue
            best = None
            best_area = -1
            for m in mons:
                mx, my, mw, mh = m["left"], m["top"], m["width"], m["height"]
                ix = max(sx, mx)
                iy = max(sy, my)
                ex = min(sx + sw, mx + mw)
                ey = min(sy + sh, my + mh)
                area = max(0, ex - ix) * max(0, ey - iy)
                if area > best_area:
                    best_area = area
                    best = m
            out.append((s, best if best else mons[0]))
        return out

    def start(self):
        mode = self.cfg.get("capture_mode", "virtual")
        if mode == "per_screen":
            self._start_per_screen()
        else:
            self._start_virtual()

    def _start_virtual(self):
        virt = QGuiApplication.primaryScreen().virtualGeometry()
        img = self._grabber.grab_virtual()
        mapping = self._match_monitors()
        base_origin = (self._grabber._sct.monitors[0]["left"], self._grabber._sct.monitors[0]["top"])
        ov = VirtualOverlay(img, self.cfg, virt, mapping, base_origin)
        ov.captured.connect(self._on_captured)
        ov.cancel_all.connect(self.close_all)
        self._overlays = [ov]
        ov.show()
        ov.raise_()

    def _start_per_screen(self):
        mapping = self._match_monitors()
        for s, mon in mapping:
            img = self._grabber.grab(s)
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

    def _on_captured(self, qimg: QImage):
        self.captured.emit(qimg)


class Launcher(QWidget):
    start_capture = Signal()
    toggle_shape = Signal()

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SlipSnap")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(240, 85)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background: rgba(25, 25, 30, 240);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            QToolButton {
                background: rgba(40, 40, 45, 120);
                border: none;
                border-radius: 12px;
                padding: 8px;
                color: #e5e7eb;
                font-weight: 500;
                font-size: 11px;
            }
            QToolButton:hover {
                background: rgba(70, 130, 240, 200);
                color: white;
            }
            QToolButton:pressed {
                background: rgba(60, 120, 220, 255);
            }
            QLabel {
                color: #f9fafb;
                font-size: 14px;
                font-weight: 600;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        title = QLabel("SlipSnap")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        btns = QHBoxLayout()
        btns.setSpacing(8)

        self.btn_capture = QToolButton()
        self.btn_capture.setIcon(make_icon_capture())
        self.btn_capture.setIconSize(QSize(20, 20))
        self.btn_capture.setText("Снимок")
        self.btn_capture.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_capture.clicked.connect(self.start_capture.emit)
        btns.addWidget(self.btn_capture)

        self.btn_shape = QToolButton()
        self.btn_shape.setIcon(make_icon_shape(self.cfg.get("shape", "rect")))
        self.btn_shape.setIconSize(QSize(20, 20))
        self.btn_shape.setText("Круг" if self.cfg.get("shape", "rect") == "ellipse" else "Квадрат")
        self.btn_shape.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_shape.clicked.connect(self._on_shape)
        btns.addWidget(self.btn_shape)

        self.btn_close = QToolButton()
        self.btn_close.setIcon(make_icon_close())
        self.btn_close.setIconSize(QSize(20, 20))
        self.btn_close.setText("Закрыть")
        self.btn_close.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_close.clicked.connect(self.close)
        btns.addWidget(self.btn_close)

        layout.addLayout(btns)
        main_layout.addWidget(container)

        self._drag_pos = None
        scr = QGuiApplication.primaryScreen().geometry()
        self.move(scr.center().x() - self.width() // 2, scr.top() + 100)

        # Добавляем тень
        self.setGraphicsEffect(self._create_shadow_effect())

    def _create_shadow_effect(self):
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 6)
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


class App(QObject):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.launcher = Launcher(self.cfg)
        self.launcher.start_capture.connect(self.capture)
        self.launcher.toggle_shape.connect(self._toggle_shape)
        self.launcher.show()

    def _toggle_shape(self):
        if hasattr(self, "ovm"):
            self.ovm.set_shape(self.cfg.get("shape", "rect"))

    def capture(self):
        try:
            self.ovm = OverlayManager(self.cfg)
            self.ovm.captured.connect(self._on_captured)
            self.ovm.start()
        except Exception as e:
            QMessageBox.critical(None, "SlipSnap", f"Ошибка съёмки: {e}")

    def _on_captured(self, qimg: QImage):
        try:
            self.ovm.close_all()
        except Exception:
            pass
        try:
            img = qimage_to_pil(qimg)
            save_history(img)
            EditorWindow(qimg, self.cfg).show()
        except Exception as e:
            QMessageBox.critical(None, "SlipSnap", f"Ошибка обработки: {e}")
