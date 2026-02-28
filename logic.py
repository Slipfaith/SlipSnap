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

from design_tokens import Typography, Metrics
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
    "last_save_directory": str(Path.home()),
    "video_duration_sec": 6,
    "video_fps": 15,
    "video_default_format": "mp4",
    "video_last_save_directory": str(Path.home()),
    "ffmpeg_path": "",
    "series_prefix": "Series",
    "series_folder": str(Path.home()),
    "tesseract_path": "",
    "tessdata_prefix": "",
    "meme_dialog_width": Metrics.MEME_DIALOG_MIN_WIDTH,
    "meme_dialog_height": Metrics.MEME_DIALOG_MIN_HEIGHT,
    "zoom_lens_size": 90,
    "zoom_lens_factor": 2.0,
    "ocr_settings": {
        "preferred_languages": ["eng"],
        "last_language": "auto",
        "auto_config": True,
        "psm": None,
        "oem": None,
    },
}


def _clamp_int(value, default: int, min_value: int, max_value: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = int(default)
    return max(min_value, min(max_value, number))


def _clamp_float(value, default: float, min_value: float, max_value: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = float(default)
    return max(min_value, min(max_value, number))


def _normalize_video_config(cfg: dict) -> None:
    cfg["video_duration_sec"] = _clamp_int(cfg.get("video_duration_sec"), 6, 5, 10)
    cfg["video_fps"] = _clamp_int(cfg.get("video_fps"), 15, 10, 24)

    fmt = str(cfg.get("video_default_format", "mp4")).strip().lower()
    cfg["video_default_format"] = fmt if fmt in {"mp4", "gif"} else "mp4"

    try:
        out_dir = Path(str(cfg.get("video_last_save_directory", Path.home()))).expanduser()
    except Exception:
        out_dir = Path.home()
    if not out_dir.exists() or not out_dir.is_dir():
        out_dir = Path.home()
    cfg["video_last_save_directory"] = str(out_dir)

    try:
        ffmpeg_candidate = Path(str(cfg.get("ffmpeg_path", "")).strip()).expanduser()
    except Exception:
        ffmpeg_candidate = Path("")
    if ffmpeg_candidate and ffmpeg_candidate.exists() and ffmpeg_candidate.is_file():
        cfg["ffmpeg_path"] = str(ffmpeg_candidate)
    else:
        cfg["ffmpeg_path"] = ""

    cfg["meme_dialog_width"] = _clamp_int(
        cfg.get("meme_dialog_width"),
        Metrics.MEME_DIALOG_MIN_WIDTH,
        Metrics.MEME_DIALOG_MIN_WIDTH,
        2200,
    )
    cfg["meme_dialog_height"] = _clamp_int(
        cfg.get("meme_dialog_height"),
        Metrics.MEME_DIALOG_MIN_HEIGHT,
        Metrics.MEME_DIALOG_MIN_HEIGHT,
        1600,
    )
    cfg["zoom_lens_size"] = _clamp_int(cfg.get("zoom_lens_size"), 90, 60, 260)
    cfg["zoom_lens_factor"] = _clamp_float(cfg.get("zoom_lens_factor"), 2.0, 1.2, 8.0)

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
    _normalize_video_config(cfg)
    return cfg

def save_config(cfg: dict) -> None:
    safe_cfg = copy.deepcopy(cfg)
    _normalize_video_config(safe_cfg)
    data = copy.deepcopy(DEFAULT_CONFIG)
    for key, default_value in DEFAULT_CONFIG.items():
        if key not in safe_cfg:
            continue
        value = safe_cfg[key]
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

    @staticmethod
    def _score_screen_monitor_pair(screen, mon: dict, logical_virtual, physical_virtual: dict) -> float:
        g = screen.geometry()
        logical_w = max(1.0, float(logical_virtual.width()))
        logical_h = max(1.0, float(logical_virtual.height()))
        phys_w = max(1.0, float(physical_virtual["width"]))
        phys_h = max(1.0, float(physical_virtual["height"]))

        sx = (float(g.x()) + float(g.width()) * 0.5 - float(logical_virtual.x())) / logical_w
        sy = (float(g.y()) + float(g.height()) * 0.5 - float(logical_virtual.y())) / logical_h
        mx = (
            float(mon["left"]) + float(mon["width"]) * 0.5 - float(physical_virtual["left"])
        ) / phys_w
        my = (
            float(mon["top"]) + float(mon["height"]) * 0.5 - float(physical_virtual["top"])
        ) / phys_h

        center_score = abs(sx - mx) + abs(sy - my)

        g_ar = max(1e-6, float(g.width()) / max(1.0, float(g.height())))
        m_ar = max(1e-6, float(mon["width"]) / max(1.0, float(mon["height"])))
        aspect_score = abs(math.log(g_ar / m_ar))

        scale_x = float(mon["width"]) / max(1.0, float(g.width()))
        scale_y = float(mon["height"]) / max(1.0, float(g.height()))
        scale_score = abs(scale_x - scale_y)

        return center_score + (aspect_score * 0.2) + (scale_score * 0.1)

    def match_screens_to_monitors(self) -> list[tuple[object, dict]]:
        from PySide6.QtGui import QGuiApplication

        self._refresh_monitors()
        screens = list(QGuiApplication.screens())
        monitors = list(self._monitors)
        if not screens or not monitors:
            return []

        primary = QGuiApplication.primaryScreen()
        if primary is not None:
            logical_virtual = primary.virtualGeometry()
        else:
            logical_virtual = screens[0].geometry()
            for s in screens[1:]:
                logical_virtual = logical_virtual.united(s.geometry())

        try:
            all_monitors = self._sct.monitors if self._sct is not None else []
        except Exception:
            all_monitors = []
        if all_monitors:
            physical_virtual = all_monitors[0]
        else:
            left = min(m["left"] for m in monitors)
            top = min(m["top"] for m in monitors)
            right = max(m["left"] + m["width"] for m in monitors)
            bottom = max(m["top"] + m["height"] for m in monitors)
            physical_virtual = {
                "left": left,
                "top": top,
                "width": max(1, right - left),
                "height": max(1, bottom - top),
            }

        pairs: list[tuple[float, int, int]] = []
        for si, s in enumerate(screens):
            for mi, mon in enumerate(monitors):
                score = self._score_screen_monitor_pair(s, mon, logical_virtual, physical_virtual)
                pairs.append((score, si, mi))
        pairs.sort(key=lambda item: item[0])

        mapping: dict[int, int] = {}
        used_monitors: set[int] = set()
        for _score, si, mi in pairs:
            if si in mapping or mi in used_monitors:
                continue
            mapping[si] = mi
            used_monitors.add(mi)
            if len(mapping) == len(screens):
                break

        for si, s in enumerate(screens):
            if si in mapping:
                continue
            available = [idx for idx in range(len(monitors)) if idx not in used_monitors]
            if not available:
                available = list(range(len(monitors)))
            best_idx = min(
                available,
                key=lambda idx: self._score_screen_monitor_pair(
                    s, monitors[idx], logical_virtual, physical_virtual
                ),
            )
            mapping[si] = best_idx
            used_monitors.add(best_idx)

        return [(screens[si], monitors[mapping[si]]) for si in range(len(screens))]

    def _match_monitor(self, qs) -> Optional[dict]:
        mapping = self.match_screens_to_monitors()
        if not mapping:
            return None
        for screen, mon in mapping:
            if screen is qs:
                return mon
        target_geom = qs.geometry()
        for screen, mon in mapping:
            if screen.geometry() == target_geom:
                return mon
        return mapping[0][1]

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
