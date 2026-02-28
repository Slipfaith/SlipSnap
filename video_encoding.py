from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


class VideoEncodingError(RuntimeError):
    """Base error for video encoding failures."""


class FFmpegUnavailableError(VideoEncodingError):
    """Raised when ffmpeg is not installed or cannot be executed."""


def _bundled_ffmpeg_candidates() -> list[Path]:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.extend(
            [
                base / "ffmpeg.exe",
                base / "ffmpeg" / "ffmpeg.exe",
                base / "bin" / "ffmpeg.exe",
            ]
        )

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / "ffmpeg.exe",
                exe_dir / "ffmpeg" / "ffmpeg.exe",
                exe_dir / "bin" / "ffmpeg.exe",
            ]
        )

    module_dir = Path(__file__).resolve().parent
    candidates.extend(
        [
            module_dir / "ffmpeg.exe",
            module_dir / "ffmpeg" / "ffmpeg.exe",
            module_dir / "bin" / "ffmpeg.exe",
        ]
    )
    return candidates


def find_ffmpeg_binary() -> Optional[str]:
    env_override = os.environ.get("SLIPSNAP_FFMPEG_PATH", "").strip()
    if env_override:
        candidate = Path(env_override)
        if candidate.is_file():
            return str(candidate)

    seen: set[str] = set()
    for candidate in _bundled_ffmpeg_candidates():
        try:
            resolved = str(candidate.resolve())
        except Exception:
            resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.is_file():
            return str(candidate)

    return shutil.which("ffmpeg")


def ensure_ffmpeg_available(ffmpeg_bin: Optional[str] = None) -> str:
    binary = ffmpeg_bin or find_ffmpeg_binary()
    if not binary:
        raise FFmpegUnavailableError(
            "FFmpeg не найден. Установите ffmpeg и добавьте его в PATH."
        )
    try:
        subprocess.run(
            [binary, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5,
        )
    except Exception as exc:
        raise FFmpegUnavailableError(
            "FFmpeg найден, но не запускается. Проверьте установку и PATH."
        ) from exc
    return binary


class MP4StreamEncoder:
    """Stream raw RGB frames to ffmpeg and produce an MP4 file."""

    def __init__(
        self,
        width: int,
        height: int,
        fps: int,
        output_path: Path,
        ffmpeg_bin: Optional[str] = None,
    ):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.output_path = Path(output_path)
        self.ffmpeg_bin = ensure_ffmpeg_available(ffmpeg_bin)
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self._proc is not None:
            return
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-video_size",
            f"{self.width}x{self.height}",
            "-framerate",
            str(self.fps),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            # yuv420p requires even frame dimensions; pad by 1px when needed.
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(self.output_path),
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def write_frame(self, rgb_bytes: bytes) -> None:
        if self._proc is None:
            self.start()
        if self._proc is None or self._proc.stdin is None:
            raise VideoEncodingError("FFmpeg процесс не инициализирован.")
        try:
            self._proc.stdin.write(rgb_bytes)
        except (BrokenPipeError, OSError) as exc:
            raise VideoEncodingError("Ошибка записи кадра в ffmpeg.") from exc

    def finalize(self) -> None:
        proc = self._proc
        if proc is None:
            raise VideoEncodingError("FFmpeg процесс не был запущен.")
        stderr_text = ""
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            stderr_raw = b""
            if proc.stderr is not None:
                stderr_raw = proc.stderr.read()
            rc = proc.wait(timeout=60)
            stderr_text = stderr_raw.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            self._proc = None
            raise VideoEncodingError("Не удалось завершить кодирование MP4.") from exc

        self._proc = None
        if rc != 0:
            tail = stderr_text[-600:] if stderr_text else ""
            raise VideoEncodingError(
                "FFmpeg завершился с ошибкой при сохранении MP4."
                + (f"\n{tail}" if tail else "")
            )

    def abort(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


def convert_mp4_to_gif(
    source_mp4: Path,
    target_gif: Path,
    fps: int = 10,
    ffmpeg_bin: Optional[str] = None,
) -> None:
    source_mp4 = Path(source_mp4)
    target_gif = Path(target_gif)
    if not source_mp4.exists():
        raise VideoEncodingError("Исходный MP4 для конвертации в GIF не найден.")
    binary = ensure_ffmpeg_available(ffmpeg_bin)
    gif_fps = max(1, min(int(fps), 24))
    target_gif.parent.mkdir(parents=True, exist_ok=True)
    palette = target_gif.parent / f".{target_gif.stem}.palette.png"
    try:
        _run_ffmpeg(
            [
                binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source_mp4),
                "-vf",
                f"fps={gif_fps},palettegen",
                str(palette),
            ],
            "Не удалось сгенерировать палитру GIF.",
        )
        _run_ffmpeg(
            [
                binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source_mp4),
                "-i",
                str(palette),
                "-filter_complex",
                f"fps={gif_fps}[x];[x][1:v]paletteuse",
                "-loop",
                "0",
                str(target_gif),
            ],
            "Не удалось сохранить GIF.",
        )
    finally:
        try:
            palette.unlink(missing_ok=True)
        except Exception:
            pass


def _run_ffmpeg(cmd: list[str], context_message: str) -> None:
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
    except Exception as exc:
        raise VideoEncodingError(context_message) from exc

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        tail = stderr[-600:] if stderr else ""
        raise VideoEncodingError(
            context_message + (f"\n{tail}" if tail else "")
        )
