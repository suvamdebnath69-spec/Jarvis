"""Jarvis voice - streaming neural text-to-speech.

Voice providers, in priority order:
  1. ElevenLabs (if ELEVENLABS_API_KEY is set) - the iconic conversational
     JARVIS voice. Free tier available at elevenlabs.io.
  2. Microsoft Edge neural voices (free, no API key) via edge-tts.
  3. System pyttsx3 voice (offline fallback).

Chunks are spoken on a background worker thread as fast as they arrive, so
JARVIS can start speaking while the model is still generating.

Env vars:
    ELEVENLABS_API_KEY   your ElevenLabs key (free at elevenlabs.io)
    ELEVENLABS_VOICE     voice id (default: the JARVIS conversational voice)
    ELEVENLABS_MODEL     default eleven_turbo_v2_5 (lowest latency)
    JARVIS_VOICE         edge-tts voice, e.g. en-US-AriaNeural (fallback)
    JARVIS_VOICE_RATE    edge-tts rate modifier (default -8%)
"""

import os
import queue
import tempfile
import threading
import time

import requests

from env import load_env
load_env()

VOICE_NAME = os.environ.get("JARVIS_VOICE", "en-US-AriaNeural")
RATE = os.environ.get("JARVIS_VOICE_RATE", "-8%")  # edge-tts rate modifier

# ElevenLabs (used when a key is present)
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
# The well-known ElevenLabs JARVIS conversational voice (community voice)
ELEVENLABS_VOICE = os.environ.get(
    "ELEVENLABS_VOICE", "JBF_dEiPT3w5jBBS5k4kY")
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5")


class StreamingVoice:
    """Speak text chunks in order on a background thread, as fast as they come."""

    def __init__(self, voice=VOICE_NAME):
        self.voice = voice
        self.q = queue.Queue(maxsize=4)
        self._edge = None
        self._mixer = None
        self._fallback = None
        self._fallback_lock = threading.Lock()

        try:
            import edge_tts
            self._edge = edge_tts
        except ImportError:
            pass
        try:
            import pygame
            pygame.mixer.init()
            self._mixer = pygame.mixer
        except Exception:
            self._mixer = None

        self._worker = threading.Thread(target=self._run, daemon=True,
                                        name="jarvis-tts")
        self._worker.start()

    # -- public API -------------------------------------------------------
    def say(self, text):
        """Queue a chunk to be spoken (non-blocking)."""
        text = (text or "").strip()
        if text:
            try:
                self.q.put_nowait(text)
            except queue.Full:
                pass  # drop rather than stall the model

    def wait(self):
        """Block until everything queued has been spoken."""
        self.q.join()

    def stop(self):
        """Silence immediately and drop pending chunks."""
        if self._mixer is not None:
            try:
                self._mixer.music.stop()
            except Exception:
                pass
        while True:
            try:
                self.q.get_nowait()
                self.q.task_done()
            except queue.Empty:
                break

    # -- internals --------------------------------------------------------
    def _run(self):
        while True:
            chunk = self.q.get()
            if chunk is None:
                self.q.task_done()
                break
            try:
                self._play(chunk)
            finally:
                self.q.task_done()

    def _synth_mp3(self, text, path):
        import asyncio

        async def go():
            com = self._edge.Communicate(text, self.voice, rate=RATE)
            await com.save(path)

        asyncio.run(go())

    def _synth_mp3_eleven(self, text, path):
        """Synthesize with ElevenLabs (conversational JARVIS voice)."""
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/"
               f"{ELEVENLABS_VOICE}")
        headers = {"xi-api-key": ELEVENLABS_API_KEY,
                   "Accept": "audio/mpeg",
                   "Content-Type": "application/json"}
        payload = {"text": text, "model_id": ELEVENLABS_MODEL,
                   "voice_settings": {"stability": 0.5,
                                      "similarity_boost": 0.75,
                                      "style": 0.3,
                                      "use_speaker_boost": True}}
        r = requests.post(url, headers=headers, json=payload, timeout=30,
                          stream=True)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

    def _play(self, text):
        if self._mixer is not None:
            fd, path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            try:
                if ELEVENLABS_API_KEY:
                    self._synth_mp3_eleven(text, path)   # ElevenLabs first
                else:
                    raise RuntimeError("no elevenlabs key")
                self._mixer.music.load(path)
                self._mixer.music.play()
                while self._mixer.music.get_busy():
                    time.sleep(0.05)
                return
            except Exception:
                self._mixer.music.stop()
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if self._edge is not None:                    # fall back to edge-tts
                fd, path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)
                try:
                    self._synth_mp3(text, path)
                    self._mixer.music.load(path)
                    self._mixer.music.play()
                    while self._mixer.music.get_busy():
                        time.sleep(0.05)
                    return
                except Exception:
                    self._mixer.music.stop()
                finally:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        self._fallback_speak(text)

    def _fallback_speak(self, text):
        with self._fallback_lock:
            if self._fallback is None:
                import pyttsx3
                self._fallback = pyttsx3.init()
                try:
                    voices = self._fallback.getProperty("voices")
                    if voices:
                        self._fallback.setProperty("voice", voices[0].id)
                    self._fallback.setProperty("rate", 175)
                except Exception:
                    pass
            self._fallback.say(text)
            self._fallback.runAndWait()
