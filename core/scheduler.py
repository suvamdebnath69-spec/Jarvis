"""
scheduler.py — NOVA's sense of time.

Two independent duties, both on a background thread so they never get
blocked by NOVA being busy or mid-conversation:

  1. One-shot reminders ("remind me to X in 10 minutes") — announced
     through the speaker and pushed to the UI when due.
  2. Recurring wellbeing nudges — no LLM involved, plain timers:
       - every 30 minutes  -> drink water
       - every 60 minutes  -> back to studying
       - after 23:00       -> go to sleep (once per day)

Pending tasks persist to logs/tasks.json across restarts.
"""

import json
import threading
import time

import config
from core.state import state
from core.tts import voice


class Scheduler:
    WATER_EVERY = 30 * 60        # seconds
    STUDY_EVERY = 60 * 60        # seconds
    SLEEP_AFTER_HOUR = 23        # 11 PM

    def __init__(self):
        self._reminders = []     # [{when, text}]
        self._lock = threading.Lock()
        self._last_water = time.time()
        self._last_study = time.time()
        self._last_sleep_day = None
        self._load_tasks()

    # ---------------------------------------------------------- persistence ----
    def _load_tasks(self):
        try:
            with open(config.TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            state.pending_tasks = data.get("pending", [])
        except Exception:
            pass

    def _save_tasks(self):
        try:
            with open(config.TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump({"pending": state.get_tasks()["pending"]}, f, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------- reminders ----
    def add_reminder(self, when: float, text: str):
        with self._lock:
            self._reminders.append({"when": when, "text": text})
            self._reminders.sort(key=lambda r: r["when"])
        state.add_pending(f"Reminder: {text}")

    def _announce(self, text: str):
        state.add_announcement(text)
        voice.say(text)

    def _check_due(self):
        now = time.time()
        due = []
        with self._lock:
            while self._reminders and self._reminders[0]["when"] <= now:
                due.append(self._reminders.pop(0))
        for r in due:
            self._announce(f"Reminder, sir: {r['text']}")
            self._save_tasks()

    # ----------------------------------------------------- recurring nudges ----
    def _wellbeing(self):
        now = time.time()
        if now - self._last_water >= self.WATER_EVERY:
            self._last_water = now
            self._announce("Time for some water, sir. Hydration keeps the machine running.")
        if now - self._last_study >= self.STUDY_EVERY:
            self._last_study = now
            self._announce("A gentle nudge, sir — your studies await.")
        lt = time.localtime()
        if lt.tm_hour >= self.SLEEP_AFTER_HOUR and self._last_sleep_day != lt.tm_mday:
            self._last_sleep_day = lt.tm_mday
            self._announce("It's past eleven, sir. Even I recommend sleep — and I never sleep at all.")

    # --------------------------------------------------------------- loop ----
    def _loop(self):
        while True:
            try:
                self._check_due()
                self._wellbeing()
            except Exception:
                pass
            time.sleep(1)

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()


scheduler = Scheduler()
