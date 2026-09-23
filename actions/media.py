"""
media.py — local media control via Windows media keys.

Uses the virtual-key API (VK_MEDIA_PLAY_PAUSE etc.) through keybd_event,
so it works with Spotify, VLC, browsers — anything honoring media keys.
No internet, no LLM, no per-app integration.
"""

from core.state import state

_VK_PLAY_PAUSE = 0xB3
_VK_NEXT = 0xB0
_VK_PREV = 0xB1
_VK_STOP = 0xB2

_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002


def _send_media_key(vk: int) -> bool:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, _KEYEVENTF_EXTENDEDKEY, 0)
        user32.keybd_event(vk, 0, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


def play_music():
    if _send_media_key(_VK_PLAY_PAUSE):
        return "Playing, sir."
    return "I couldn't reach the media keys on this machine, sir."


def pause_music():
    if _send_media_key(_VK_PLAY_PAUSE):
        return "Paused, sir."
    return "The media keys didn't respond, sir."


def next_track():
    if _send_media_key(_VK_NEXT):
        return "Skipping ahead, sir."
    return "I couldn't skip the track, sir."


def prev_track():
    if _send_media_key(_VK_PREV):
        return "Back to the previous track, sir."
    return "I couldn't go back a track, sir."


def stop_media():
    if _send_media_key(_VK_STOP):
        return "Stopped, sir."
    return "The media keys didn't respond, sir."
