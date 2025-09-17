# -*- coding: utf-8 -*-

import sys
import warnings


if sys.platform.startswith("win"):
    from .win import WinKeyBinder

    keybinder = WinKeyBinder()
else:

    class _UnavailableKeyBinder:
        """Fallback keybinder used on unsupported platforms."""

        def init(self):
            warnings.warn(
                "Global hotkeys are only available on Windows in this build of "
                "pyqtkeybind.",
                RuntimeWarning,
                stacklevel=2,
            )

        def register_hotkey(self, *args, **kwargs):
            warnings.warn(
                "Global hotkeys are only available on Windows in this build of "
                "pyqtkeybind.",
                RuntimeWarning,
                stacklevel=2,
            )
            return False

        def unregister_hotkey(self, *args, **kwargs):
            return False

        def handler(self, *args, **kwargs):
            return False

    keybinder = _UnavailableKeyBinder()


__all__ = ["keybinder"]
