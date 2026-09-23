"""
hotkey.py — global Ctrl+J to start/open NOVA.

Registers a system-wide hotkey with the OS (user32.RegisterHotKey) inside
a dedicated message-loop thread — zero third-party packages. While NOVA
is running, Ctrl+J anywhere in Windows opens (or refocuses) NOVA's UI.

For the cold case (NOVA not running at all), install_autostart.py puts
the same Ctrl+J hotkey on a desktop shortcut that boots NOVA; the
duplicate-instance guard in main.py makes both mechanisms coexist.
"""

import os
import threading

MOD_CONTROL = 0x0002
VK_J = 0x4A
WM_HOTKEY = 0x0312
HOTKEY_ID = 0x4E4F  # "NO"


def start_hotkey(callback):
    """Register Ctrl+J globally; call `callback()` on every press."""
    if os.name != "nt":
        return None
    thread = threading.Thread(target=_loop, args=(callback,), daemon=True)
    thread.start()
    return thread


def _loop(callback):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL, VK_J):
        # Expected when the desktop shortcut (NOVA.lnk) owns Ctrl+J —
        # the second-instance guard in main.py opens the UI for us.
        print("Ctrl+J is owned by the desktop shortcut — warm launches open the UI via main.py's guard.")
        return

    print("Global hotkey Ctrl+J is live — press it anywhere to open NOVA.")
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == WM_HOTKEY:
            try:
                callback()
            except Exception as e:
                print("Hotkey action failed:", e)

    user32.UnregisterHotKey(None, HOTKEY_ID)
