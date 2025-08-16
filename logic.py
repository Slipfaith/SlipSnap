import json
import math
import uuid
import tempfile
from pathlib import Path
from typing import Tuple, Optional
import mss
from PIL import Image, ImageQt

APP_NAME = "Screenshot"
CONFIG_PATH = Path.home() / ".screenshot_config.json"
HISTORY_DIR = Path(tempfile.gettempdir()) / "screenshot_history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "shape": "rect",
    "blur_radius": 6,
    "tesseract_path": ""
}

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            base = DEFAULT_CONFIG.copy()
            base.update(cfg)
            return base
        except Exception:
            pass
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def pil_to_qpixmap(img: Image.Image):
    from PySide6.QtGui import QPixmap
    return QPixmap.fromImage(ImageQt.ImageQt(img.convert("RGBA")))

def qimage_to_pil(qimg) -> Image.Image:
    from PySide6.QtGui import QImage
    buf = qimg.bits().tobytes()
    return Image.frombuffer("RGBA", (qimg.width(), qimg.height()), buf, "raw", "BGRA", 0, 1)

def save_history(img: Image.Image) -> Path:
    p = HISTORY_DIR / f"shot_{uuid.uuid4().hex}.png"
    img.save(p)
    return p

def smart_grid(n: int) -> Tuple[int, int]:
    if n <= 2:
        return (n, 1)
    if n == 3:
        return (3, 1)
    if n == 4:
        return (2, 2)
    if n in (5, 6):
        return (3, 2)
    c = math.ceil(math.sqrt(n))
    r = math.ceil(n / c)
    return c, r

class ScreenGrabber:
    def __init__(self):
        self._sct = mss.mss()
        self._monitors = self._sct.monitors[1:]

    def _match_monitor(self, qs) -> Optional[dict]:
        from PySide6.QtCore import QRect
        g = qs.geometry()
        for mon in self._monitors:
            if (mon["left"] == g.x() and mon["top"] == g.y() and
                mon["width"] == g.width() and mon["height"] == g.height()):
                return mon
        for mon in self._monitors:
            r1 = QRect(mon["left"], mon["top"], mon["width"], mon["height"])
            if r1.intersects(g):
                return mon
        return None

    def grab(self, qs) -> Image.Image:
        mon = self._match_monitor(qs)
        if not mon:
            raise RuntimeError("Не удалось сопоставить монитор MSS с QScreen")
        shot = self._sct.grab(mon)
        return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)