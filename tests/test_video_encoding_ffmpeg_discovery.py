from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import video_encoding
from video_encoding import find_ffmpeg_binary


class VideoEncodingFFmpegDiscoveryTests(unittest.TestCase):
    def test_env_override_has_priority(self) -> None:
        env_ffmpeg = Path(r"C:\test\ffmpeg.exe")

        def _is_file(path_obj: Path) -> bool:
            return str(path_obj) == str(env_ffmpeg)

        with (
            patch.dict(os.environ, {"SLIPSNAP_FFMPEG_PATH": str(env_ffmpeg)}),
            patch("video_encoding.Path.is_file", autospec=True, side_effect=_is_file),
            patch("video_encoding.shutil.which", return_value=None),
        ):
            resolved = find_ffmpeg_binary()
        self.assertEqual(Path(resolved), env_ffmpeg)

    def test_detects_bundled_meipass_ffmpeg(self) -> None:
        meipass = Path(r"C:\bundle")
        bundled_ffmpeg = meipass / "ffmpeg.exe"

        def _is_file(path_obj: Path) -> bool:
            return str(path_obj) == str(bundled_ffmpeg)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(video_encoding.sys, "_MEIPASS", str(meipass), create=True),
            patch("video_encoding.Path.is_file", autospec=True, side_effect=_is_file),
            patch("video_encoding.shutil.which", return_value=None),
        ):
            resolved = find_ffmpeg_binary()
        self.assertEqual(Path(resolved), bundled_ffmpeg)

    def test_falls_back_to_system_path(self) -> None:
        fake = Path(r"C:\ffmpeg\bin\ffmpeg.exe")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("video_encoding.Path.is_file", autospec=True, return_value=False),
            patch("video_encoding.shutil.which", return_value=str(fake)),
        ):
            resolved = find_ffmpeg_binary()
        self.assertEqual(Path(resolved), fake)


if __name__ == "__main__":
    unittest.main()
