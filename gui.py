# -*- coding: utf-8 -*-
from typing import List
from PIL import Image, ImageFilter, ImageDraw, ImageQt
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, Signal, QObject, QSize
from PySide6.QtGui import QGuiApplication, QPainter, QPen, QColor, QPixmap, QImage
from PySide6.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout, QToolButton, QMessageBox)
from logic import load_config, save_config, ScreenGrabber, qimage_to_pil, save_history
from editor import EditorWindow
from icons import make_icon_capture, make_icon_shape, make_icon_close


class SingleOverlay(QWidget):
    captured = Signal(QImage)
    cancel_all = Signal()

    def __init__(self, screen, base_img: Image.Image, cfg: dict):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setScreen(screen)
        self.setFocusPolicy(Qt.StrongFocus)

        self.cfg = cfg
        self.shape = cfg.get("shape", "rect")
        self.base_img = base_img.convert("RGBA")
        self.blurred = self.base_img.filter(ImageFilter.GaussianBlur(radius=cfg.get("blur_radius", 6)))
        self.bg_blurred = QPixmap.fromImage(ImageQt.ImageQt(self.blurred))
        self.bg_original = QPixmap.fromImage(ImageQt.ImageQt(self.base_img))

        geo = screen.geometry()
        self.setGeometry(geo)
        self.screen_offset_x = geo.x()
        self.screen_offset_y = geo.y()

        self.origin = QPoint()
        self.current = QPoint()
        self.selecting = False

        self.help = QLabel(self)
        self.help.setText("🖱️ Выделить область  •  ⎵ Сменить форму  •  ⎋ Отмена")
        self.help.setStyleSheet("""
            color: white; 
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(0, 0, 0, 200),
                stop:1 rgba(20, 20, 30, 200)); 
            padding: 10px 15px; 
            font-size: 13px; 
            border-radius: 8px;
            border: 1px solid rgba(80, 80, 90, 100);
        """)
        self.help.adjustSize()
        self.help.move(30, 30)

    def showEvent(self, e):
        super().showEvent(e)
        self.activateWindow()
        self.raise_()
        self.grabKeyboard()

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
            rect = self._norm(self.origin, self.current)
            if rect.width() > 5 and rect.height() > 5:
                x = rect.x() - self.screen_offset_x
                y = rect.y() - self.screen_offset_y
                w, h = rect.width(), rect.height()
                x, y = max(0, x), max(0, y)
                w = min(w, self.width() - x)
                h = min(h, self.height() - y)

                crop = self.base_img.crop((x, y, x + w, y + h))

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
        p.drawPixmap(self.rect(), self.bg_blurred)

        if self.selecting:
            rect = self._norm(self.origin, self.current)
            local_rect = QRect(
                rect.x() - self.screen_offset_x,
                rect.y() - self.screen_offset_y,
                rect.width(),
                rect.height()
            )

            if self.shape == "rect":
                p.drawPixmap(local_rect, self.bg_original, local_rect)
                p.setPen(QPen(QColor(255, 255, 255), 2, Qt.DashLine))
                p.drawRect(local_rect)
            else:
                from PySide6.QtGui import QPainterPath
                clip_path = QPainterPath()
                clip_path.addEllipse(QRectF(local_rect))
                p.save()
                p.setClipPath(clip_path)
                p.drawPixmap(local_rect, self.bg_original, local_rect)
                p.restore()

                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255), 2, Qt.DashLine))
                p.drawEllipse(QRectF(local_rect))

        p.end()


class OverlayManager(QObject):
    captured = Signal(QImage)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._grabber = ScreenGrabber()
        self._overlays: List[SingleOverlay] = []

    def start(self):
        for screen in QGuiApplication.screens():
            img = self._grabber.grab(screen)
            ov = SingleOverlay(screen, img, self.cfg)
            ov.captured.connect(self._on_captured)
            ov.cancel_all.connect(self.close_all)
            ov.showFullScreen()
            self._overlays.append(ov)

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

        self.setFixedSize(240, 80)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(45, 45, 50, 240),
                    stop:1 rgba(25, 25, 30, 240));
                border-radius: 20px;
                border: 1px solid rgba(80, 80, 90, 100);
            }
            QToolButton {
                background: rgba(60, 60, 70, 100);
                border: 1px solid rgba(80, 80, 90, 80);
                border-radius: 12px;
                padding: 8px;
                color: white;
                font-weight: 500;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(90, 140, 220, 180),
                    stop:1 rgba(70, 120, 200, 180));
                border: 1px solid rgba(120, 160, 240, 150);
            }
            QToolButton:pressed {
                background: rgba(50, 100, 180, 200);
            }
            QLabel {
                color: rgba(200, 200, 210, 180);
                font-size: 11px;
                font-weight: 400;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)

        title = QLabel("SlipSnap")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: rgba(220, 220, 230, 200); font-size: 13px; font-weight: 600; margin-bottom: 2px;")
        layout.addWidget(title)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        self.btn_capture = QToolButton()
        self.btn_capture.setIcon(make_icon_capture())
        self.btn_capture.setIconSize(QSize(24, 24))
        self.btn_capture.setToolTip("Сделать скриншот")
        self.btn_capture.clicked.connect(self.start_capture.emit)
        self.btn_capture.setText("Снимок")
        self.btn_capture.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        buttons_layout.addWidget(self.btn_capture)

        self.btn_shape = QToolButton()
        self.btn_shape.setIcon(make_icon_shape(self.cfg.get("shape", "rect")))
        self.btn_shape.setIconSize(QSize(24, 24))
        shape_text = "Круг" if self.cfg.get("shape", "rect") == "ellipse" else "Квадрат"
        self.btn_shape.setText(shape_text)
        self.btn_shape.setToolTip("Переключить форму выделения")
        self.btn_shape.clicked.connect(self._on_shape)
        self.btn_shape.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        buttons_layout.addWidget(self.btn_shape)

        self.btn_close = QToolButton()
        self.btn_close.setIcon(make_icon_close())
        self.btn_close.setIconSize(QSize(24, 24))
        self.btn_close.setText("Закрыть")
        self.btn_close.setToolTip("Закрыть приложение")
        self.btn_close.clicked.connect(self.close)
        self.btn_close.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        buttons_layout.addWidget(self.btn_close)

        layout.addLayout(buttons_layout)
        main_layout.addWidget(container)

        self.make_draggable()

        scr = QGuiApplication.primaryScreen().geometry()
        self.move(scr.center().x() - self.width() // 2, scr.top() + 100)

    def make_draggable(self):
        self.drag_position = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def _on_shape(self):
        self.cfg["shape"] = "ellipse" if self.cfg.get("shape", "rect") == "rect" else "rect"
        save_config(self.cfg)
        self.btn_shape.setIcon(make_icon_shape(self.cfg["shape"]))
        shape_text = "Круг" if self.cfg["shape"] == "ellipse" else "Квадрат"
        self.btn_shape.setText(shape_text)
        self.toggle_shape.emit()


class App(QObject):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.launcher = Launcher(self.cfg)
        self.launcher.start_capture.connect(self.capture)
        self.launcher.show()

    def capture(self):
        try:
            self.ovm = OverlayManager(self.cfg)
            self.ovm.captured.connect(self._on_captured)
            self.ovm.start()
        except Exception as e:
            QMessageBox.critical(None, "Screenshot", f"Ошибка съёмки: {e}")

    def _on_captured(self, qimg: QImage):
        self.ovm.close_all()
        img = qimage_to_pil(qimg)
        save_history(img)
        EditorWindow(qimg, self.cfg).show()