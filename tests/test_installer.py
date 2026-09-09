from __future__ import annotations

import unittest
from pathlib import Path


class InstallerTests(unittest.TestCase):
    def test_autostart_is_an_optional_installer_task(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "SlipSnap.iss").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn('Name: "autostart"', script)
        self.assertIn("Flags: unchecked", script)
        self.assertIn('Name: "{userstartup}\\SlipSnap"', script)
        self.assertIn("Tasks: autostart", script)


if __name__ == "__main__":
    unittest.main()
