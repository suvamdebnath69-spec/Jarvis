"""
registry.py — NOVA's action registry.

One place maps intents to local handlers. Adding a capability means adding
one entry here — no new elif chain in main.py.

Each entry:
    handler(text, params) -> (reply, route_tag)

route_tag is one of:
    "local"   — executed fully locally (no LLM, no web)
    "web"     — required external/web data
    "llm"     — required the local LLM
    "confirm" — pending user confirmation (dangerous action)
    "error"   — handler failed / unknown
"""

import re
import threading
import time

import config
from core.state import state

# --------------------------------------------------------- pending confirmations ----
_CONFIRM_LOCK = threading.Lock()
_pending = None          # {"kind": ..., "desc": ..., "expires": ...} for power actions
_pending_delete = None   # {"path": ..., "name": ...} for file deletes


def set_pending(kind: str, desc: str):
    """Store a pending dangerous action (10s expiry so stale confirms die)."""
    global _pending, _pending_delete
    with _CONFIRM_LOCK:
        _pending = {"kind": kind, "desc": desc, "expires": time.time() + 15}
        _pending_delete = None


def set_pending_delete(descriptor: dict):
    global _pending, _pending_delete
    with _CONFIRM_LOCK:
        _pending_delete = dict(descriptor)
        _pending_delete["expires"] = time.time() + 15
        _pending = None


def peek_pending():
    with _CONFIRM_LOCK:
        p = _pending or _pending_delete
        if p and p.get("expires", 0) > time.time():
            return dict(p)
        return None


def consume_pending():
    """Pop the pending action (or None) — 'confirm' path only."""
    global _pending, _pending_delete
    with _CONFIRM_LOCK:
        p, _pending, _pending_delete = _pending or _pending_delete, None, None
        if p and p.get("expires", 0) > time.time():
            return p
        return None


def cancel_pending():
    global _pending, _pending_delete
    with _CONFIRM_LOCK:
        p, _pending, _pending_delete = _pending or _pending_delete, None, None
        return p


# --------------------------------------------------------------- logging ----
_LOG_PATH = None


def _route_log():
    global _LOG_PATH
    if _LOG_PATH is None:
        import os

        _LOG_PATH = os.path.join(config.LOGS_DIR, "routing.log")
    return _LOG_PATH


def log_route(text, intent, confidence, source, route, used_llm=False, used_web=False,
              error=None):
    """One line per command: how it was understood, where it ran, what happened."""
    entry = (
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} | intent={intent} conf={confidence:.2f} "
        f"source={source} route={route} llm={int(used_llm)} web={int(used_web)} "
        f"error={error or '-'} | {text[:80]}"
    )
    try:
        with open(_route_log(), "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass


# ----------------------------------------------------------- confirmation flow ----
_CONFIRM_WORDS = re.compile(r"^(?:confirm|yes|do it|go ahead|confirmed)\b", re.I)
_CANCEL_WORDS = re.compile(r"^(?:cancel|no|stop|abort|never\s?mind|don'?t)\b", re.I)


def is_confirm(text: str) -> bool:
    return bool(_CONFIRM_WORDS.match((text or "").strip()))


def is_cancel(text: str) -> bool:
    return bool(_CANCEL_WORDS.match((text or "").strip()))
