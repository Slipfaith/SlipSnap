# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logic import MEME_DIR


class LogicPathTests(unittest.TestCase):
    def test_meme_dir_is_not_temporary(self) -> None:
        legacy_temp_dir = Path(tempfile.gettempdir()) / "slipsnap_memes"
        self.assertNotEqual(MEME_DIR, legacy_temp_dir)


if __name__ == "__main__":
    unittest.main()
