def translate_hotkey(qt_hotkey_str: str) -> str:
    """Translates a Qt-style hotkey string to a pynput-style hotkey string."""
    parts = qt_hotkey_str.lower().split('+')
    pynput_parts = []
    for part in parts:
        part = part.strip()
        if part in ('ctrl', 'alt', 'shift', 'cmd'):
            pynput_parts.append(f'<{part}>')
        else:
            pynput_parts.append(part)
    return '+'.join(pynput_parts)
