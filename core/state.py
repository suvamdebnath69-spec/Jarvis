"""
state.py — NOVA's shared runtime state.

One thread-safe object holds everything the UI and the brain agree on:
current status (listening / thinking / speaking / idle), conversation
history, the task list, and live system stats. The Flask endpoints read
from here; the brain and scheduler write to it.
"""

import threading
import time
from collections import deque


class NovaState:
    def __init__(self, history_limit=200):
        self._lock = threading.Lock()
        self._history_limit = history_limit

        self.status = "idle"            # idle | listening | thinking | speaking
        self.status_detail = "NOVA is ready"
        self.history = deque(maxlen=history_limit)   # [{role, text, time, intent}]
        self.ongoing_tasks = []         # [{title, category, progress}]
        self.pending_tasks = []         # [str]
        self.announcements = deque(maxlen=50)        # reminders & proactive msgs
        self._announcement_id = 0
        self.stats = {"cpu": 0, "ram": 0, "storage": 0, "overall": 0, "battery": None}
        self.voice_enabled = True
        self.beast_mode = False   # Beast Mode: expanded tool access when armed

    # ------------------------------------------------------------ status ----
    def set_status(self, status, detail=""):
        with self._lock:
            self.status = status
            if detail:
                self.status_detail = detail

    def get_status(self):
        with self._lock:
            return self.status, self.status_detail

    # ----------------------------------------------------------- history ----
    def add_message(self, role, text, intent=None):
        with self._lock:
            self.history.append(
                {"role": role, "text": text, "intent": intent, "time": time.time()}
            )

    def get_history(self, limit=40):
        with self._lock:
            return list(self.history)[-limit:]

    # ---------------------------------------------------------- reminders ----
    def add_announcement(self, text):
        """Store an announcement permanently-ish; clients read by cursor."""
        with self._lock:
            self._announcement_id += 1
            self.announcements.append(
                {"id": self._announcement_id, "text": text, "time": time.time()}
            )

    def announcements_since(self, since_id=0):
        """
        Non-destructive read: everything newer than the client's cursor.
        Returns (items, latest_id) so no client ever misses a reminder that
        fired while it wasn't looking.
        """
        with self._lock:
            items = [dict(a) for a in self.announcements if a["id"] > since_id]
            return items, self._announcement_id

    # ------------------------------------------------------------- tasks ----
    def add_task(self, title, category="General", progress=0):
        with self._lock:
            self.ongoing_tasks.append(
                {"title": title, "category": category, "progress": progress}
            )

    def complete_task(self, title):
        with self._lock:
            for t in self.ongoing_tasks:
                if t["title"].lower() == title.lower():
                    t["progress"] = 100
                    self.pending_tasks.append(t["title"] + " (done)")
                    self.ongoing_tasks.remove(t)
                    return True
            return False

    def add_pending(self, title):
        with self._lock:
            self.pending_tasks.append(title)

    def get_tasks(self):
        with self._lock:
            return {
                "ongoing": [dict(t) for t in self.ongoing_tasks],
                "pending": list(self.pending_tasks),
            }

    # ------------------------------------------------------------- stats ----
    def set_stats(self, **kwargs):
        with self._lock:
            self.stats.update(kwargs)

    def get_stats(self):
        with self._lock:
            return dict(self.stats)

    # -------------------------------------------------------------- misc ----
    def set_voice_enabled(self, enabled):
        with self._lock:
            self.voice_enabled = bool(enabled)

    def voice_on(self):
        with self._lock:
            return self.voice_enabled

    # -------------------------------------------------------- beast mode ----
    def set_beast_mode(self, enabled):
        with self._lock:
            self.beast_mode = bool(enabled)

    def beast_armed(self):
        with self._lock:
            return self.beast_mode


# single shared instance for the whole app
state = NovaState()
