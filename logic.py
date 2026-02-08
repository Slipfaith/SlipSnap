from __future__ import annotations

import copy
import json
import math
import uuid
import tempfile
from pathlib import Path
from typing import Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QRect

import mss
from PIL import Image

from design_tokens import Typography
APP_NAME = "SlipSnap"
APP_VERSION = "2.2"
CONFIG_PATH = Path.home() / ".slipsnap_config.json"
HISTORY_DIR = Path(tempfile.gettempdir()) / "slipsnap_history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
MEME_DIR = Path(tempfile.gettempdir()) / "slipsnap_memes"
MEME_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "shape": "rect",
    "pen_width": 3,
    "font_px": Typography.TEXT_TOOL_DEFAULT_POINT,
    "capture_hotkey": "Ctrl+Alt+S",
    "series_prefix": "Series",
    "series_folder": str(Path.home()),
    "tesseract_path": "",
    "tessdata_prefix": "",
    "ocr_settings": {
        "preferred_languages": ["eng"],
        "last_language": "auto",
        "auto_config": True,
        "psm": None,
        "oem": None,
    },
}

def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, default_value in DEFAULT_CONFIG.items():
                    if key not in data:
                        continue
                    user_value = data[key]
                    if isinstance(default_value, dict) and isinstance(user_value, dict):
                        merged = default_value.copy()
                        merged.update({k: v for k, v in user_value.items() if k in default_value})
                        cfg[key] = merged
                    elif not isinstance(default_value, dict):
                        cfg[key] = user_value
        except Exception:
            pass
    return cfg

def save_config(cfg: dict) -> None:
    data = copy.deepcopy(DEFAULT_CONFIG)
    for key, default_value in DEFAULT_CONFIG.items():
        if key not in cfg:
            continue
        value = cfg[key]
        if isinstance(default_value, dict) and isinstance(value, dict):
            merged = default_value.copy()
            merged.update({k: v for k, v in value.items() if k in default_value})
            data[key] = merged
        elif not isinstance(default_value, dict):
            data[key] = value
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def pil_to_qpixmap(img: Image.Image):
    """Convert PIL image to QPixmap with RGBA support."""
    from PySide6.QtGui import QImage, QPixmap

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, w, h, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)

def qimage_to_pil(qimg) -> Image.Image:
    from PySide6.QtGui import QImage
    if qimg.isNull():
        raise ValueError("QImage is null")
    if qimg.format() != QImage.Format_RGBA8888:
        qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    bpl = qimg.bytesPerLine()
    try:
        size = qimg.sizeInBytes()
    except AttributeError:
        size = bpl * h
    ptr = qimg.constBits()
    buf = bytes(ptr[:size])
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "RGBA", bpl, 1)
    return img.copy()

def save_history(img: Image.Image) -> Path:
    p = HISTORY_DIR / f"shot_{uuid.uuid4().hex}.png"
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img.save(p, format="PNG")
    _prune_history(keep=10)
    return p

def _prune_history(keep: int = 10) -> None:
    files = sorted(
        [*HISTORY_DIR.glob("*.png"), *HISTORY_DIR.glob("*.jpg"), *HISTORY_DIR.glob("*.jpeg")],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    for f in files[keep:]:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

def smart_grid(n: int) -> Tuple[int, int]:
    if n <= 0:
        return (0, 0)
    cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    return rows, cols

class ScreenGrabber:
    def __init__(self):
        self._sct = mss.mss()
        self._monitors = []
        self._refresh_monitors()

    def _refresh_monitors(self) -> None:
        """Refresh cached monitor information from the MSS backend."""

        try:
            monitors = self._sct.monitors
        except Exception:
            monitors = None

        if monitors:
            # ``monitors`` returns a list where index 0 is the virtual monitor
            # spanning all screens. Keep only physical monitors for matching.
            self._monitors = [m for m in monitors[1:]]
        else:
            self._monitors = []

    def _qt_rect_phys(self, qs) -> QRect:
        from PySide6.QtCore import QRect
        g = qs.geometry()
        dpr = getattr(qs, "devicePixelRatio", lambda: 1.0)()
        if hasattr(qs, "devicePixelRatio"):
            try:
                dpr = float(qs.devicePixelRatio())
            except Exception:
                dpr = 1.0
        left = int(round(g.x() * dpr))
        top = int(round(g.y() * dpr))
        width = int(round(g.width() * dpr))
        height = int(round(g.height() * dpr))
        return QRect(left, top, width, height)

    def _match_monitor(self, qs) -> Optional[dict]:
        from PySide6.QtCore import QRect
        target = self._qt_rect_phys(qs)
        for mon in self._monitors:
            if (mon["left"] == target.x() and mon["top"] == target.y()
                and mon["width"] == target.width() and mon["height"] == target.height()):
                return mon
        best = None
        best_area = -1
        for mon in self._monitors:
            mr = QRect(mon["left"], mon["top"], mon["width"], mon["height"])
            inter = mr.intersected(target)
            area = inter.width() * inter.height()
            if area > best_area:
                best_area = area
                best = mon
        return best

    def grab(self, qs) -> Image.Image:
        self._refresh_monitors()
        mon = self._match_monitor(qs)
        if not mon:
            raise RuntimeError("Не удалось сопоставить монитор MSS с QScreen")
        shot = self._sct.grab(mon)
        return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)

    def grab_virtual(self) -> Image.Image:
        self._refresh_monitors()
        monitors = self._sct.monitors
        if not monitors:
            raise RuntimeError("Не удалось получить список мониторов MSS")
        mon = monitors[0]
        shot = self._sct.grab(mon)
        return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
