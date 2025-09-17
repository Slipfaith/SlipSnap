# -*- coding: utf-8 -*-

import ctypes
from ctypes import windll

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

from .keycodes import KeyTbl, ModsTbl


def keys_from_string(keys):
    keysequence = QKeySequence(keys)
    ks = keysequence[0]

    # Calculate the modifiers
    mods = 0
    qtmods = 0
    try:
        shift = int(Qt.ShiftModifier)
        alt = int(Qt.AltModifier)
        ctrl = int(Qt.ControlModifier)
    except TypeError:
        # PySide 6.7+ returns QtCore.Qt.KeyboardModifier instances that are no
        # longer directly convertible to ``int``.  Fall back to their numeric
        # value to keep backward compatibility with older releases.
        shift = Qt.ShiftModifier.value
        alt = Qt.AltModifier.value
        ctrl = Qt.ControlModifier.value

    if ks & shift == shift:
        mods |= ModsTbl.index(Qt.ShiftModifier)
        qtmods |= shift
    if ks & alt == alt:
        mods |= ModsTbl.index(Qt.AltModifier)
        qtmods |= alt
    if ks & ctrl == ctrl:
        mods |= ModsTbl.index(Qt.ControlModifier)
        qtmods |= ctrl

    # Calculate the keys
    qtkeys = ks ^ qtmods
    try:
        keys = KeyTbl[qtkeys]
        if keys == 0:
            keys = _get_virtual_key(qtkeys)
    except ValueError:
        keys = _get_virtual_key(qtkeys)
    except IndexError:
        keys = KeyTbl.index(qtkeys)
        if keys == 0:
            keys = _get_virtual_key(qtkeys)


    return mods, keys


def _get_virtual_key(qtkeys):
    """Use the system keyboard layout to retrieve the virtual key.

    Fallback when we're unable to find a keycode in the mappings table.
    """
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    thread_id = 0

    # Key table doesn't have an entry for this keycode
    # Attempt to retrieve the VK code from system
    keyboard_layout = user32.GetKeyboardLayout(thread_id)
    virtual_key = windll.user32.VkKeyScanExW(qtkeys, keyboard_layout)
    if virtual_key == -1:
        keyboard_layout = user32.GetKeyboardLayout(0x409)
        virtual_key = windll.user32.VkKeyScanExW(qtkeys, keyboard_layout)
    # Key code is the low order byte
    keys = virtual_key & 0xff

    return keys
