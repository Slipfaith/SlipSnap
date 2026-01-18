from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageEnhance, ImageFilter
from PySide6.QtGui import QImage

import pytesseract
from pytesseract import TesseractError, TesseractNotFoundError

from logic import qimage_to_pil, save_config

import os
import shutil
import threading
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

_TESSERACT_DOWNLOAD_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
_TESSDATA_FAST_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main"


# На Windows скрываем всплывающие консольные окна Tesseract
if os.name == "nt":
    _existing_kwargs = getattr(pytesseract.pytesseract, "popen_kwargs", {})
    _popen_kwargs = dict(_existing_kwargs) if isinstance(_existing_kwargs, dict) else {}

    # Блокируем создание консольного окна даже на доли секунды.
    # combination of CREATE_NO_WINDOW + скрытый STARTUPINFO помогает
    # и при установке tesseract_cmd пользователем.
    _popen_kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    if "startupinfo" not in _popen_kwargs:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        _popen_kwargs["startupinfo"] = startup

    pytesseract.pytesseract.popen_kwargs = _popen_kwargs

    # Дополнительно патчим subprocess.Popen, чтобы любые внутренние вызовы
    # (включая subprocess.run) Tesseract не всплывали отдельным окном.
_AVAILABLE_LANG_CACHE: Optional[List[str]] = None
_WARMUP_LOCK = threading.Lock()
_WARMUP_STARTED = False
_TESSERACT_CONFIGURED = False


LANGUAGE_DISPLAY_NAMES = {
    "eng": "English",
    "rus": "Russian",
    "deu": "German",
    "fra": "French",
    "spa": "Spanish",
    "ita": "Italian",
    "por": "Portuguese",
    "ukr": "Ukrainian",
    "pol": "Polish",
    "nld": "Dutch",
    "tur": "Turkish",
    "ara": "Arabic",
    "heb": "Hebrew",
    "jpn": "Japanese",
    "kor": "Korean",
    "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)",
}


def get_language_display_name(code: str) -> str:
    normalized = str(code).strip()
    if not normalized:
        return ""
    return LANGUAGE_DISPLAY_NAMES.get(normalized, normalized)


def _set_tesseract_cmd(path: str) -> None:
    pytesseract.pytesseract.tesseract_cmd = path


def _candidate_paths_from_roots(roots: Iterable[str]) -> List[str]:
    candidates: List[str] = []
    for root in roots:
        root_path = Path(root)
        if not root_path:
            continue
        candidates.append(str(root_path / "Tesseract-OCR" / "tesseract.exe"))
        candidates.append(str(root_path / "Programs" / "Tesseract-OCR" / "tesseract.exe"))
    return candidates


def _find_tesseract_in_path() -> Optional[str]:
    result = shutil.which("tesseract")
    return result if result else None


def _find_tesseract_in_standard_locations() -> Optional[str]:
    if os.name != "nt":
        return None
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for candidate in _candidate_paths_from_roots([root for root in roots if root]):
        if os.path.exists(candidate):
            return candidate
    return None


def _get_configured_path(cfg: Optional[dict]) -> Optional[str]:
    if not isinstance(cfg, dict):
        return None
    path = cfg.get("tesseract_path")
    if not isinstance(path, str) or not path.strip():
        return None
    normalized = str(Path(path))
    if os.path.exists(normalized):
        return normalized
    return None


def _apply_tessdata_prefix(cfg: Optional[dict]) -> None:
    if not isinstance(cfg, dict):
        return
    prefix = cfg.get("tessdata_prefix")
    if not isinstance(prefix, str) or not prefix.strip():
        return
    prefix_path = Path(prefix).expanduser()
    if prefix_path.exists():
        os.environ["TESSDATA_PREFIX"] = str(prefix_path)


def _prompt_for_tesseract(parent: Optional[QWidget]) -> Optional[str]:
    dialog = QMessageBox(parent)
    dialog.setWindowTitle("SlipSnap · OCR")
    dialog.setIcon(QMessageBox.Warning)
    dialog.setText("Tesseract OCR не найден.")
    dialog.setInformativeText(
        "Вы можете указать путь к tesseract.exe вручную или перейти к установке."
    )
    choose_btn = dialog.addButton("Указать путь", QMessageBox.ActionRole)
    install_btn = dialog.addButton("Перейти к установке", QMessageBox.ActionRole)
    dialog.addButton(QMessageBox.Cancel)
    dialog.exec()

    clicked = dialog.clickedButton()
    if clicked is choose_btn:
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Выберите tesseract.exe",
            str(Path.home()),
            "tesseract.exe (tesseract.exe);;Все файлы (*)",
        )
        if file_path and os.path.exists(file_path):
            return file_path
        if file_path:
            QMessageBox.warning(
                parent,
                "SlipSnap · OCR",
                "Указанный файл не найден. Проверьте путь к tesseract.exe.",
            )
    elif clicked is install_btn:
        QDesktopServices.openUrl(QUrl(_TESSERACT_DOWNLOAD_URL))
    return None


def configure_tesseract(cfg: Optional[dict], parent: Optional[QWidget] = None) -> bool:
    global _TESSERACT_CONFIGURED
    if _TESSERACT_CONFIGURED:
        return True

    _apply_tessdata_prefix(cfg)

    configured_path = _get_configured_path(cfg)
    if configured_path:
        _set_tesseract_cmd(configured_path)
        _TESSERACT_CONFIGURED = True
        return True

    path_from_env = _find_tesseract_in_path()
    if path_from_env:
        _set_tesseract_cmd(path_from_env)
        if isinstance(cfg, dict):
            cfg["tesseract_path"] = path_from_env
            save_config(cfg)
        _TESSERACT_CONFIGURED = True
        return True

    path_from_default = _find_tesseract_in_standard_locations()
    if path_from_default:
        _set_tesseract_cmd(path_from_default)
        if isinstance(cfg, dict):
            cfg["tesseract_path"] = path_from_default
            save_config(cfg)
        _TESSERACT_CONFIGURED = True
        return True

    if parent is not None or QApplication.instance() is not None:
        manual_path = _prompt_for_tesseract(parent)
        if manual_path:
            _set_tesseract_cmd(manual_path)
            if isinstance(cfg, dict):
                cfg["tesseract_path"] = manual_path
                save_config(cfg)
            _TESSERACT_CONFIGURED = True
            return True
    return False


class OcrError(RuntimeError):
    """User-facing OCR errors with actionable messaging."""


@dataclass
class OcrWord:
    text: str
    bbox: Tuple[int, int, int, int]
    line_id: Tuple[int, int, int]


@dataclass
class OcrResult:
    text: str
    language_tag: str
    missing_languages: List[str] = field(default_factory=list)
    fallback_used: bool = False
    warnings: List[str] = field(default_factory=list)
    languages_used: List[str] = field(default_factory=list)
    words: List[OcrWord] = field(default_factory=list)


@dataclass
class OcrSettings:
    preferred_languages: List[str] = field(default_factory=lambda: ["eng"])
    last_language: str = "auto"
    auto_config: bool = True
    psm: Optional[int] = None
    oem: Optional[int] = None

    @classmethod
    def from_config(cls, cfg: dict) -> "OcrSettings":
        data = cfg.get("ocr_settings") if isinstance(cfg, dict) else None
        if not isinstance(data, dict):
            data = {}
        preferred = data.get("preferred_languages")
        if not isinstance(preferred, list):
            preferred = ["eng"]
        preferred = [str(lang).strip() for lang in preferred if str(lang).strip()]
        if not preferred:
            preferred = ["eng"]
        last_language = data.get("last_language", "auto")
        if not isinstance(last_language, str) or not last_language.strip():
            last_language = "auto"
        auto_config = data.get("auto_config", True)
        if not isinstance(auto_config, bool):
            auto_config = True
        psm = data.get("psm")
        if not isinstance(psm, int):
            psm = None
        oem = data.get("oem")
        if not isinstance(oem, int):
            oem = None
        return cls(
            preferred_languages=preferred,
            last_language=last_language,
            auto_config=auto_config,
            psm=psm,
            oem=oem,
        )

    def to_dict(self) -> dict:
        return {
            "preferred_languages": list(self.preferred_languages),
            "last_language": self.last_language,
            "auto_config": self.auto_config,
            "psm": self.psm,
            "oem": self.oem,
        }

    def remember_run(self, requested: str, languages_used: Sequence[str]) -> None:
        if requested:
            self.last_language = requested
        used = [str(lang).strip() for lang in languages_used if str(lang).strip()]
        if used:
            seen = set()
            ordered = []
            for lang in used:
                if lang not in seen:
                    ordered.append(lang)
                    seen.add(lang)
            self.preferred_languages = ordered


@dataclass
class OcrLanguageDownload:
    installed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    failed_details: List[Tuple[str, str]] = field(default_factory=list)


LangHint = Optional[Union[str, Sequence[str]]]


@dataclass
class OcrPreprocessTransform:
    scale: float
    rotation: int
    scaled_size: Tuple[int, int]
    original_size: Tuple[int, int]


def _ensure_pil_image(image: Union[Image.Image, QImage]) -> Image.Image:
    if isinstance(image, Image.Image):
        return image
    if isinstance(image, QImage):
        return qimage_to_pil(image)
    raise OcrError("Передано неподдерживаемое изображение для OCR")


def _build_tesseract_config(psm: Optional[int], oem: Optional[int]) -> str:
    parts: List[str] = []
    if psm is not None:
        parts.extend(["--psm", str(psm)])
    if oem is not None:
        parts.extend(["--oem", str(oem)])
    return " ".join(parts)


def _scale_for_ocr(image: Image.Image) -> Tuple[Image.Image, float]:
    dpi_info = image.info.get("dpi")
    scale = 1.0
    if isinstance(dpi_info, (tuple, list)) and len(dpi_info) >= 2:
        try:
            dpi_x = float(dpi_info[0])
            dpi_y = float(dpi_info[1])
        except (TypeError, ValueError):
            dpi_x = 0.0
            dpi_y = 0.0
        min_dpi = min(val for val in (dpi_x, dpi_y) if val > 0) if dpi_x and dpi_y else 0.0
        if min_dpi:
            scale = min(3.0, max(1.0, 300.0 / min_dpi))
    else:
        scale = 2.0

    if scale <= 1.05:
        return image, 1.0
    new_size = (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale))))
    return image.resize(new_size, Image.LANCZOS), scale


def _otsu_threshold(image: Image.Image) -> Image.Image:
    histogram = image.histogram()
    if len(histogram) < 256:
        return image
    total = sum(histogram[:256])
    if total == 0:
        return image
    sum_total = sum(i * histogram[i] for i in range(256))
    sum_background = 0.0
    weight_background = 0.0
    max_variance = -1.0
    threshold = 0
    for i in range(256):
        weight_background += histogram[i]
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += i * histogram[i]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = i
    return image.point(lambda x: 255 if x > threshold else 0, mode="L")


def _deskew_with_tesseract(image: Image.Image) -> Tuple[Image.Image, int]:
    try:
        osd = pytesseract.image_to_osd(image)
    except Exception:
        return image, 0
    rotation = 0
    for line in osd.splitlines():
        if "Rotate:" in line:
            try:
                rotation = int(line.split(":", 1)[1].strip())
            except (TypeError, ValueError):
                rotation = 0
            break
    rotation = rotation % 360
    if rotation not in (0, 90, 180, 270):
        return image, 0
    applied = (360 - rotation) % 360
    if applied == 0:
        return image, 0
    return image.rotate(applied, expand=True), applied


def _preprocess_for_ocr(pil_image: Image.Image) -> Tuple[Image.Image, OcrPreprocessTransform]:
    original_size = pil_image.size
    image = pil_image.convert("L")
    image, scale = _scale_for_ocr(image)
    scaled_size = image.size
    image = image.filter(ImageFilter.MedianFilter(size=3))
    image = ImageEnhance.Contrast(image).enhance(1.5)
    image = image.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=3))
    image, rotation = _deskew_with_tesseract(image)
    image = _otsu_threshold(image)
    transform = OcrPreprocessTransform(
        scale=scale,
        rotation=rotation,
        scaled_size=scaled_size,
        original_size=original_size,
    )
    return image, transform


def _inverse_rotate_point(x: float, y: float, rotation: int, size: Tuple[int, int]) -> Tuple[float, float]:
    width, height = size
    if rotation == 90:
        return (width - 1) - y, x
    if rotation == 180:
        return (width - 1) - x, (height - 1) - y
    if rotation == 270:
        return y, (height - 1) - x
    return x, y


def _map_bbox_to_original(
    bbox: Tuple[int, int, int, int],
    transform: OcrPreprocessTransform,
) -> Tuple[int, int, int, int]:
    x, y, w, h = bbox
    x1 = float(x)
    y1 = float(y)
    x2 = float(x + w)
    y2 = float(y + h)
    points = [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
    if transform.rotation:
        points = [
            _inverse_rotate_point(px, py, transform.rotation, transform.scaled_size)
            for px, py in points
        ]
    if transform.scale and transform.scale != 1.0:
        points = [(px / transform.scale, py / transform.scale) for px, py in points]
    xs = [px for px, _ in points]
    ys = [py for _, py in points]
    min_x = max(0.0, min(xs))
    min_y = max(0.0, min(ys))
    max_x = min(float(transform.original_size[0]), max(xs))
    max_y = min(float(transform.original_size[1]), max(ys))
    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    return (
        int(round(min_x)),
        int(round(min_y)),
        int(round(width)),
        int(round(height)),
    )


def _score_ocr_data(data: dict) -> float:
    try:
        confs = data.get("conf", [])
    except AttributeError:
        return 0.0
    numeric_confs = []
    for raw in confs:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            numeric_confs.append(value)
    if not numeric_confs:
        return 0.0
    avg_conf = sum(numeric_confs) / len(numeric_confs)
    word_count = sum(1 for raw in data.get("text", []) if str(raw).strip())
    return avg_conf + min(20.0, word_count * 0.2)


def _select_best_config(
    pil_image: Image.Image,
    lang_value: Optional[str],
    settings: OcrSettings,
) -> Tuple[str, Optional[dict]]:
    if not settings.auto_config:
        config = _build_tesseract_config(settings.psm, settings.oem)
        try:
            data = pytesseract.image_to_data(
                pil_image,
                lang=lang_value or None,
                config=config or "",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            data = None
        return config, data

    candidates = [
        (3, 3),
        (6, 3),
        (7, 3),
        (11, 3),
    ]
    best_config = ""
    best_data = None
    best_score = -1.0
    for psm, oem in candidates:
        config = _build_tesseract_config(psm, oem)
        try:
            data = pytesseract.image_to_data(
                pil_image,
                lang=lang_value or None,
                config=config or "",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            continue
        score = _score_ocr_data(data)
        if score > best_score:
            best_score = score
            best_config = config
            best_data = data
    if best_score < 0:
        return "", None
    return best_config, best_data


def _normalize_languages(language_hint: LangHint, settings: OcrSettings, available: Sequence[str]) -> Tuple[Optional[str], List[str], List[str]]:
    if isinstance(language_hint, str):
        hint = language_hint.strip()
        if not hint or hint.lower() == "auto":
            parsed = []
        else:
            parsed = [part.strip() for part in hint.replace(",", "+").split("+") if part.strip()]
    elif isinstance(language_hint, (list, tuple, set)):
        parsed = [str(lang).strip() for lang in language_hint if str(lang).strip()]
    else:
        parsed = []

    if not parsed:
        parsed = list(settings.preferred_languages)

    normalized = []
    seen = set()
    for lang in parsed:
        if lang and lang not in seen:
            normalized.append(lang)
            seen.add(lang)

    missing = [lang for lang in normalized if available and lang not in available]
    usable = [lang for lang in normalized if not available or lang in available]
    lang_string = "+".join(usable) if usable else None
    return lang_string, missing, usable


def _get_tesseract_cmd() -> str:
    cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", "") or ""
    return cmd if cmd else "tesseract"


def _get_fallback_tessdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    base_path = Path(base) if base else Path.home()
    return base_path / "SlipSnap" / "tessdata"


def _seed_fallback_tessdata(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for trained in source.glob("*.traineddata"):
        target = destination / trained.name
        if target.exists():
            continue
        try:
            shutil.copy2(trained, target)
        except OSError:
            continue


def _persist_tessdata_prefix(cfg: Optional[dict], prefix: Path) -> None:
    if not isinstance(cfg, dict):
        return
    cfg["tessdata_prefix"] = str(prefix)
    save_config(cfg)


def _get_tessdata_dir() -> Path:
    prefix = os.environ.get("TESSDATA_PREFIX")
    if prefix:
        prefix_path = Path(prefix).expanduser()
        if prefix_path.exists():
            return prefix_path

    cmd = _get_tesseract_cmd()
    popen_kwargs = getattr(pytesseract.pytesseract, "popen_kwargs", {})
    try:
        result = subprocess.run(
            [cmd, "--print-tessdata-dir"],
            check=True,
            capture_output=True,
            text=True,
            **(popen_kwargs if isinstance(popen_kwargs, dict) else {}),
        )
        output = (result.stdout or "").strip()
        if output:
            tessdata_dir = Path(output).expanduser()
            if tessdata_dir.exists():
                return tessdata_dir
    except Exception:
        pass

    cmd_path = Path(cmd).expanduser()
    if cmd_path.exists():
        candidate = cmd_path.parent / "tessdata"
        if candidate.exists():
            return candidate

    raise OcrError("Не удалось определить папку tessdata для Tesseract.")


def download_tesseract_languages(
    languages: Sequence[str],
    *,
    progress: Optional[Callable[[int, int, str], bool]] = None,
    cfg: Optional[dict] = None,
) -> OcrLanguageDownload:
    normalized = []
    seen = set()
    for lang in languages:
        code = str(lang).strip()
        if code and code not in seen:
            normalized.append(code)
            seen.add(code)

    if not normalized:
        raise OcrError("Не указаны языки для загрузки.")

    tessdata_dir = _get_tessdata_dir()
    if not tessdata_dir.exists():
        raise OcrError("Папка tessdata не найдена. Проверьте установку Tesseract.")

    result = OcrLanguageDownload()
    total = len(normalized)
    fallback_dir: Optional[Path] = None

    def _activate_fallback_dir() -> Path:
        nonlocal fallback_dir, tessdata_dir
        if fallback_dir is not None:
            return fallback_dir
        fallback_dir = _get_fallback_tessdata_dir()
        fallback_dir.mkdir(parents=True, exist_ok=True)
        _seed_fallback_tessdata(tessdata_dir, fallback_dir)
        os.environ["TESSDATA_PREFIX"] = str(fallback_dir)
        _persist_tessdata_prefix(cfg, fallback_dir)
        tessdata_dir = fallback_dir
        return fallback_dir

    def _record_failure(code: str, reason: str) -> None:
        result.failed.append(code)
        result.failed_details.append((code, reason))

    for index, code in enumerate(normalized, start=1):
        if progress and not progress(index, total, code):
            raise OcrError("Загрузка языков отменена.")
        target_path = tessdata_dir / f"{code}.traineddata"
        if target_path.exists():
            result.skipped.append(code)
            continue

        url = f"{_TESSDATA_FAST_URL}/{code}.traineddata"
        request = urllib.request.Request(url, headers={"User-Agent": "SlipSnap"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            reason = f"HTTP {exc.code}: {exc.reason}" if exc.reason else f"HTTP {exc.code}"
            _record_failure(code, reason)
            continue
        except urllib.error.URLError as exc:
            reason = str(exc.reason) if getattr(exc, "reason", None) else str(exc)
            _record_failure(code, reason or "Ошибка сети")
            continue
        except Exception as exc:  # noqa: BLE001
            _record_failure(code, str(exc) or "Не удалось скачать файл")
            continue

        try:
            target_path.write_bytes(data)
        except PermissionError:
            target_path = _activate_fallback_dir() / f"{code}.traineddata"
            if target_path.exists():
                result.skipped.append(code)
                continue
            try:
                target_path.write_bytes(data)
            except OSError as exc:
                _record_failure(code, str(exc) or "Ошибка записи файла")
                continue
        except OSError as exc:
            _record_failure(code, str(exc) or "Ошибка записи файла")
            continue

        result.installed.append(code)

    if result.installed:
        global _AVAILABLE_LANG_CACHE
        _AVAILABLE_LANG_CACHE = None

    return result


def get_available_languages() -> List[str]:
    global _AVAILABLE_LANG_CACHE
    if _AVAILABLE_LANG_CACHE is not None:
        return list(_AVAILABLE_LANG_CACHE)

    try:
        langs = pytesseract.get_languages(config="")
    except TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract не найден. Укажите путь к tesseract.exe или установите Tesseract OCR."
        ) from exc
    except TesseractError:
        langs = []

    _AVAILABLE_LANG_CACHE = list(langs)
    return list(_AVAILABLE_LANG_CACHE)


def warm_up_ocr(async_run: bool = True) -> None:
    """Preload Tesseract binaries and language list to avoid first-use lag."""

    def _warm() -> None:
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            return
        try:
            get_available_languages()
        except Exception:
            pass

    global _WARMUP_STARTED
    with _WARMUP_LOCK:
        if _WARMUP_STARTED:
            return
        _WARMUP_STARTED = True

    if async_run:
        thread = threading.Thread(target=_warm, name="ocr-warmup", daemon=True)
        thread.start()
    else:
        _warm()


def run_ocr(
    image: Union[Image.Image, QImage],
    settings: OcrSettings,
    language_hint: LangHint = None,
) -> OcrResult:
    pil_image = _ensure_pil_image(image)
    processed_image, transform = _preprocess_for_ocr(pil_image)
    available = get_available_languages()
    lang_string, missing, usable_langs = _normalize_languages(language_hint, settings, available)

    try:
        pytesseract.get_tesseract_version()
    except TesseractNotFoundError as exc:
        raise OcrError(
            "Tesseract не найден. Укажите путь к tesseract.exe или установите Tesseract OCR."
        ) from exc

    def _perform(lang_value: Optional[str], config_value: str) -> str:
        return pytesseract.image_to_string(
            processed_image,
            lang=lang_value or None,
            config=config_value or "",
        )

    warnings: List[str] = []
    selected_config = ""
    data = None
    try:
        selected_config, data = _select_best_config(processed_image, lang_string, settings)
        text = _perform(lang_string, selected_config)
        language_tag = lang_string or "auto"
    except TesseractError as exc:
        if missing:
            try:
                selected_config, data = _select_best_config(processed_image, None, settings)
                text = _perform(None, selected_config)
                warnings.append(
                    "Отсутствуют языковые пакеты: "
                    + ", ".join(missing)
                    + ". Использовано автоопределение."
                )
                language_tag = "auto"
            except Exception:
                raise OcrError(
                    "Не хватает языковых данных Tesseract. Установите: " + ", ".join(missing)
                ) from exc
        else:
            raise OcrError(f"Ошибка OCR: {exc}") from exc

    if data is None:
        try:
            data = pytesseract.image_to_data(
                processed_image,
                lang=lang_string or None,
                config=selected_config or "",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            data = None

    word_data: List[OcrWord] = []

    if data and all(key in data for key in ("text", "left", "top", "width", "height", "block_num", "par_num", "line_num")):
        for i, raw_text in enumerate(data["text"]):
            text_value = str(raw_text).strip()
            if not text_value:
                continue
            try:
                bbox = (
                    int(data["left"][i]),
                    int(data["top"][i]),
                    int(data["width"][i]),
                    int(data["height"][i]),
                )
                bbox = _map_bbox_to_original(bbox, transform)
                line_id = (
                    int(data.get("block_num", [0])[i]),
                    int(data.get("par_num", [0])[i]),
                    int(data.get("line_num", [0])[i]),
                )
            except Exception:
                continue
            word_data.append(OcrWord(text=text_value, bbox=bbox, line_id=line_id))

    return OcrResult(
        text=text.strip(),
        language_tag=language_tag,
        missing_languages=missing,
        fallback_used=language_tag == "auto" and bool(missing),
        warnings=warnings,
        languages_used=usable_langs,
        words=word_data,
    )
