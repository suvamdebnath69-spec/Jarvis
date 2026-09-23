"""
beast_tools.py — the "beast mode" power tools.

These act on the whole machine, so they're kept separate from safe_tools
and some require an explicit allow flag in config before they run.

screenshot()    capture the screen to logs/
lock_pc()       lock the workstation (safe)
shutdown_pc()   power off (requires ALLOW_SHUTDOWN in config)
restart_pc()    reboot (requires ALLOW_SHUTDOWN in config)
open_task_manager()
click_window()  move the mouse and click at coordinates / on text position
type_text()     type text into the focused window
dm_instagram()  open an Instagram DM and type a message (never sends)
"""

import os
import subprocess
import time

import config

ALLOW_SHUTDOWN = False  # flip to True if you want NOVA to control power


def log_action(action: str, result: str):
    """Every Beast action gets logged (what, when, result) to logs/beast.log."""
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    with open(os.path.join(config.LOGS_DIR, "beast.log"), "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {action} | {result}\n")


def screenshot():
    try:
        import pyautogui
    except ImportError:
        return "Screenshot needs the pyautogui package installed."
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    path = os.path.join(config.LOGS_DIR, f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png")
    pyautogui.screenshot(path)
    log_action("SCREENSHOT", path)
    return f"Screenshot saved to {os.path.basename(path)}."


def lock_pc():
    if os.name != "nt":
        return "Locking only works on Windows."
    subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    log_action("LOCK_PC", "workstation locked")
    return "Locking your PC. See you soon."


def shutdown_pc():
    if not ALLOW_SHUTDOWN:
        return "Power controls are disabled in beast_tools.py — flip ALLOW_SHUTDOWN if you want them."
    subprocess.run(["shutdown", "/s", "/t", "5"],
                   creationflags=subprocess.CREATE_NO_WINDOW)
    log_action("SHUTDOWN_PC", "initiated 5s shutdown")
    return "Shutting down in 5 seconds. Goodbye."


def restart_pc():
    if not ALLOW_SHUTDOWN:
        return "Power controls are disabled in beast_tools.py — flip ALLOW_SHUTDOWN if you want them."
    subprocess.run(["shutdown", "/r", "/t", "5"],
                   creationflags=subprocess.CREATE_NO_WINDOW)
    log_action("RESTART_PC", "initiated 5s restart")
    return "Restarting in 5 seconds."


def open_task_manager():
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "taskmgr"],
                         shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        log_action("OPEN_TASK_MANAGER", "launched taskmgr")
        return "Opening task manager."
    except Exception:
        return "I couldn't open task manager."


# -------------------------------------------------------------- pc control ----

def click_window(x: int, y: int, label: str = ""):
    """Move the mouse to (x, y) and click. `label` is for the log only."""
    try:
        import pyautogui
    except ImportError:
        return "Clicking needs the pyautogui package installed."
    try:
        pyautogui.moveTo(x, y, duration=0.25)
        pyautogui.click()
        log_action("CLICK", f"({x},{y}) {label}")
        return f"Clicked {label or f'at {x}, {y}'}."
    except Exception as e:
        log_action("CLICK", f"failed: {e}")
        return "The click didn't land, sir."


def type_text(text: str, press_enter: bool = False):
    """Type `text` into whatever window has focus. Enter only on request."""
    try:
        import pyautogui
    except ImportError:
        return "Typing needs the pyautogui package installed."
    try:
        pyautogui.typewrite(text, interval=0.02)
        if press_enter:
            pyautogui.press("enter")
        log_action("TYPE", f"{len(text)} chars (enter={press_enter})")
        return "Typed."
    except Exception as e:
        log_action("TYPE", f"failed: {e}")
        return "The typing didn't land, sir."


def focus_window(title_part: str) -> bool:
    """Bring the first window whose title contains `title_part` to front."""
    try:
        import win32gui
        import win32con

        matches = []

        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title_part.lower() in title.lower():
                    matches.append(hwnd)

        win32gui.EnumWindows(_enum, None)
        if not matches:
            return False
        hwnd = matches[0]
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def dm_instagram(username: str, message: str) -> str:
    """
    Instagram DM helper: opens the chat, focuses it, clicks the message
    box and TYPES the message — but never presses Enter. You always press
    the final key yourself. (Instagram blocks logged-out automation, and
    unsolicited sending is a bot-pattern their anti-spam will punish.)
    """
    import webbrowser

    webbrowser.open(f"https://www.instagram.com/{username}/")
    time.sleep(7)  # page load
    if not focus_window(username):
        return (
            f"I opened instagram.com/{username} but couldn't focus its window, sir — "
            "you'll have to click Message yourself."
        )
    time.sleep(2)  # let the page finish painting

    # Press the page's real "Message" button, found by name via UI
    # Automation — no blind clicking at guessed coordinates.
    try:
        from pywinauto import Desktop

        window = Desktop(backend="uia").window(title_re=f".*{username}.*", found_index=0)
        msg_button = window.child_window(title_re="^Message", control_type="Button")
        msg_button.wait("exists ready", timeout=10)
        msg_button.invoke()
        time.sleep(2)  # DM pane opens
    except Exception:
        return (
            f"I opened {username}'s profile but couldn't reach the Message button, sir — "
            "it may need you to log in first."
        )

    # Type into the composer (an Edit field, found by role) or fall back
    # to raw typing if the page's DOM doesn't expose it.
    box = None
    try:
        box = window.child_window(control_type="Edit", found_index=0)
    except Exception:
        pass
    try:
        if box is not None:
            box.type_keys(message, with_spaces=True, escape_shell_chars=False)
        else:
            type_text(message)
    except Exception:
        type_text(message)
    log_action("INSTAGRAM_DM", f"to {username}: typed, NOT sent")
    return (
        f"Your message to {username} is typed in the DM box, sir — "
        "I deliberately left the sending to you."
    )