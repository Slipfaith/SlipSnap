# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import Mock

from pyqtkeybind.win import WinKeyBinder


class WinKeyBinderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.binder = WinKeyBinder()
        self.binder.RegisterHotKey = Mock(return_value=True)
        self.binder.UnregisterHotKey = Mock(return_value=True)

    def test_unregister_accepts_none_window_id(self) -> None:
        callback = Mock()
        self.assertTrue(self.binder.register_hotkey(None, "Ctrl+Alt+S", callback))
        key_index = self.binder.RegisterHotKey.call_args.args[1]

        self.assertTrue(self.binder.unregister_hotkey(None, "Ctrl+Alt+S"))

        self.binder.UnregisterHotKey.assert_called_once_with(0, key_index)
        self.assertNotIn(key_index, self.binder._WinKeyBinder__keybinds)
        self.assertNotIn(key_index, self.binder._WinKeyBinder__keygrabs)

    def test_failed_windows_unregister_keeps_callback_registry(self) -> None:
        callback = Mock()
        self.assertTrue(self.binder.register_hotkey(None, "Ctrl+Alt+S", callback))
        key_index = self.binder.RegisterHotKey.call_args.args[1]
        self.binder.UnregisterHotKey.return_value = False

        self.assertFalse(self.binder.unregister_hotkey(None, "Ctrl+Alt+S"))

        self.assertEqual(self.binder._WinKeyBinder__keybinds[key_index], [callback])
        self.assertEqual(self.binder._WinKeyBinder__keygrabs[key_index], 1)


if __name__ == "__main__":
    unittest.main()
