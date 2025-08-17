from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolBar, QApplication
from PySide6.QtGui import QImage


def size_to_image(window, qimg: QImage):
    """Resize and center the editor window to fit the image and toolbars."""
    canvas = window.canvas
    canvas.scene.setSceneRect(canvas.scene.itemsBoundingRect())

    toolbars = window.findChildren(QToolBar)
    left_w = sum(tb.sizeHint().width() for tb in toolbars if tb.orientation() == Qt.Vertical)
    top_h = sum(tb.sizeHint().height() for tb in toolbars if tb.orientation() == Qt.Horizontal)
    status_h = window.statusBar().sizeHint().height() if window.statusBar() else 0

    screen = window.screen() or QApplication.primaryScreen()
    ag = screen.availableGeometry()

    target_w = qimg.width() + left_w + 32
    target_h = qimg.height() + top_h + status_h + 32
    target_w = min(target_w, ag.width() - 40)
    target_h = min(target_h, ag.height() - 40)

    window.resize(target_w, target_h)
    window.move(ag.center().x() - window.width() // 2, ag.center().y() - window.height() // 2)
