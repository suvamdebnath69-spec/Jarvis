"""
system.py — local-first Windows system control.

Volume (pycaw), brightness (screen-brightness-control), battery/wifi
(psutil + ctypes), screenshots, media keys and power actions.

Every function returns a speakable persona string and degrades to a
helpful note (never a traceback) when a dependency/hardware is missing.

Power actions NEVER execute directly: request_power() only returns a
pending token — main.py's confirmation flow decides when to fire.
"""

import ctypes
import datetime
import os
import subprocess
import time

import psutil

import config
from core.state import state

# Power-action tokens live in state so restarts lose them automatically.
POWER_ACTIONS = {
    "shutdown": ("Shutting down the PC", ["/s"]),
    "restart": ("Restarting the PC", ["/r"]),
    "sleep": ("Putting the PC to sleep", ["/h"]),
}


# ------------------------------------------------------------------ volume ----
def _volume_endpoint():
    """(endpoint, hint) — hint is a persona note if pycaw is missing."""
    try:
        import comtypes
        from comtypes import CLSCTX_ALL
        from pycaw.constants import CLSID_MMDeviceEnumerator
        from pycaw.pycaw import EDataFlow, ERole, IAudioEndpointVolume, IMMDeviceEnumerator

        # COM must be initialized on EVERY thread that touches it — commands
        # arrive on different Flask request threads, so init unconditionally.
        # S_FALSE (already initialized) is fine.
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

        enum = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
        )
        endpoint = enum.GetDefaultAudioEndpoint(
            EDataFlow.eRender.value, ERole.eMultimedia.value
        )
        iface = endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return iface.QueryInterface(IAudioEndpointVolume), None
    except ImportError:
        return None, "Volume control needs two packages — pip install pycaw comtypes."
    except Exception as e:
        return None, f"The audio endpoint didn't cooperate, sir: {e}"


def volume_up(step: int = 10):
    ep, hint = _volume_endpoint()
    if ep is None:
        return hint
    current = ep.GetMasterVolumeLevelScalar() * 100
    ep.SetMasterVolumeLevelScalar(min(100, current + step) / 100, None)
    return f"Volume up to {min(100, int(current + step))} percent, sir."


def volume_down(step: int = 10):
    ep, hint = _volume_endpoint()
    if ep is None:
        return hint
    current = ep.GetMasterVolumeLevelScalar() * 100
    ep.SetMasterVolumeLevelScalar(max(0, current - step) / 100, None)
    return f"Volume down to {max(0, int(current - step))} percent, sir."


def set_volume(level: int):
    ep, hint = _volume_endpoint()
    if ep is None:
        return hint
    level = max(0, min(100, level))
    ep.SetMasterVolumeLevelScalar(level / 100, None)
    return f"Volume set to {level} percent, sir."


def get_volume():
    ep, hint = _volume_endpoint()
    if ep is None:
        return hint
    return f"The volume stands at {int(ep.GetMasterVolumeLevelScalar() * 100)} percent, sir."


def mute(unmute: bool = False):
    ep, hint = _volume_endpoint()
    if ep is None:
        return hint
    ep.SetMute(not unmute, None)
    return "Unmuted." if unmute else "Muted, sir. Blissful silence."


# -------------------------------------------------------------- brightness ----
def _brightness_note():
    return "Brightness control isn't available on this display, sir."


def brightness_up(step: int = 15):
    try:
        import screen_brightness_control as sbc

        current = sbc.get_brightness()[0]
        new = min(100, current + step)
        sbc.set_brightness(new)
        return f"Brightness up to {new} percent, sir."
    except Exception:
        # No external-display brightness control — use the OS media/display keys.
        try:
            import pyautogui

            for _ in range(2):
                pyautogui.hotkey("fn", "f5")  # common brightness-up combo
            return "Brightening the screen, sir."
        except Exception:
            return _brightness_note()


def brightness_down(step: int = 15):
    try:
        import screen_brightness_control as sbc

        current = sbc.get_brightness()[0]
        new = max(0, current - step)
        sbc.set_brightness(new)
        return f"Brightness down to {new} percent, sir."
    except Exception:
        return _brightness_note()


def set_brightness(level: int):
    try:
        import screen_brightness_control as sbc

        level = max(0, min(100, level))
        sbc.set_brightness(level)
        return f"Brightness set to {level} percent, sir."
    except Exception:
        return _brightness_note()


# ------------------------------------------------------------- status info ----
def battery_status():
    try:
        bat = psutil.sensors_battery()
    except Exception:
        bat = None
    if bat is None:
        return "This machine has no battery report, sir — it must run on mains power."
    status = "charging" if bat.power_plugged else "on battery"
    return f"The battery is at {round(bat.percent)} percent and {status}, sir."


def wifi_status():
    """Wi-Fi SSID via netsh (Windows) + interface-up fallback via psutil."""
    ssid = ""
    try:
        import re as _re
        import subprocess as _sp

        out = _sp.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
        m = _re.search(r"^\s*SSID\s*:\s*(.+)$", out, _re.M)
        if m:
            ssid = m.group(1).strip()
    except Exception:
        ssid = ""
    if ssid:
        return f"We're on Wi-Fi — connected to {ssid}, sir."
    # Wi-Fi unavailable/unknown: fall back to general interface state.
    try:
        up = [n for n, s in psutil.net_if_stats().items()
              if s.isup and "Loopback" not in n]
        if up:
            return f"Wi-Fi isn't connected by SSID, but {len(up)} network interface(s) are up, sir."
        return "The machine is offline, sir — no network interfaces are up."
    except Exception:
        return "I couldn't check the network just now, sir."


def lock_screen():
    if os.name != "nt":
        return "Locking only works on Windows, sir."
    try:
        subprocess.run(
            ["rundll32.exe", "user32.dll,LockWorkStation"],
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=5,
        )
        return "Locking your PC. See you soon, sir."
    except Exception:
        return "The lock command didn't land, sir."


def take_screenshot():
    try:
        import pyautogui
    except ImportError:
        return "Screenshots need the pyautogui package installed, sir."
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    path = os.path.join(config.LOGS_DIR, f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png")
    try:
        pyautogui.screenshot(path)
        return f"Screenshot saved as {os.path.basename(path)}, sir."
    except Exception as e:
        return f"The screenshot failed, sir: {e}"


# ------------------------------------------------------------------- power ----
def request_power(kind: str):
    """
    Return the metadata for a pending power action. Never executes.
    main.py stores the token and only calls execute_power() on 'confirm'.
    """
    if kind not in POWER_ACTIONS:
        return None
    return {"kind": kind, "description": POWER_ACTIONS[kind][0]}


def execute_power(kind: str):
    """Runs the actual power command — called ONLY after confirmation."""
    if kind not in POWER_ACTIONS:
        return "That power action is not on my list, sir."
    desc, args = POWER_ACTIONS[kind]
    if kind == "sleep":
        try:
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            return "Sleeping now. Wake me when you need me, sir."
        except Exception:
            return "The sleep command didn't land, sir."
    try:
        subprocess.run(["shutdown"] + args + ["/t", "5"],
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
        return f"{desc} in 5 seconds. Goodbye, sir."
    except Exception:
        return f"{desc} didn't work, sir. Perhaps permissions are against us."


# ---------------------------------------------------------------- date/time ----
def get_date():
    now = datetime.date.today()
    return f"Today is {now.strftime('%A, %B %d, %Y')}, sir."


def get_day():
    return f"It's {datetime.date.today().strftime('%A')}, sir."
