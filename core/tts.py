"""
tts.py — NOVA's voice.

A dedicated worker thread owns the pyttsx3 engine (it is not thread-safe)
and drains a speak queue, so the brain never blocks while talking. The
shared state's status flips to "speaking" while a phrase is being said and
back to "idle" when the queue is empty.
"""

import queue
import threading

import pyttsx3

import config
from core.state import state


class Speaker:
    def __init__(self):
        self._q = queue.Queue()
        self._engine = None
        self._engine_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # Warm the SAPI engine at startup so the first spoken phrase does
        # not pay the engine-creation cost (~0.5-1s) at the worst moment.
        threading.Thread(target=self._init_engine, daemon=True).start()

    def _init_engine(self):
        with self._engine_lock:
            if self._engine is not None:
                return
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", config.VOICE_RATE)
                engine.setProperty("volume", config.VOICE_VOLUME)
                voices = engine.getProperty("voices")
                if voices and config.VOICE_INDEX < len(voices):
                    engine.setProperty("voice", voices[config.VOICE_INDEX].id)
                self._engine = engine
            except Exception:
                # Engine creation can fail transiently; the worker retries
                # lazily on the next phrase.
                self._engine = None

    def _run(self):
        while True:
            phrase = self._q.get()
            if phrase is None:
                break
            if not state.voice_on():
                continue
            state.set_status("speaking", "Speaking...")
            try:
                if self._engine is None:
                    self._init_engine()
                engine = self._engine
                if engine is None:
                    continue  # no engine and couldn't create one — stay silent
                with self._engine_lock:
                    engine.say(phrase)
                    engine.runAndWait()
            except Exception:
                # Never let a voice problem kill NOVA — stay silent but alive.
                with self._engine_lock:
                    self._engine = None
            finally:
                state.set_status("idle", "NOVA is ready")

    def say(self, text):
        """Queue a phrase to be spoken aloud (non-blocking)."""
        if text:
            self._q.put(text)
    def stop(self):
        self._q.put(None)


voice = Speaker()
