"""
brain.py — NOVA's mind: local Ollama + Qwen.

Two rules keep this fast on modest hardware (i3 / 8GB / no GPU):

  1. keep_alive="30m" on EVERY call — the model stays resident in RAM
     between commands. A cold load costs ~24s on this machine; warm
     inference is ~4-6s. Never remove this from the payload.
  2. Small prompts — one-sentence persona, short history, capped output.

If Ollama is down or slow, NOVA degrades to a composed apology rather
than an error dump. Fallback chain: qwen3:1.7b -> qwen2.5:1.5b.
"""

import json
import re

import requests

import config
from core.state import state

# qwen3 sometimes leaks <think> blocks even with think:false — strip them.
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_THINK_OPEN_RE = re.compile(r"<think>.*", re.S)   # unclosed block still streaming

# For spoken output: strip markdown bullets/bold/backticks so the voice
# doesn't read "asterisk asterisk" aloud.
_MD_RE = re.compile(r"^\s*([-*•#]+|\d+\.)\s+|\*\*|`|\*", re.M)


class _StreamDead(Exception):
    """Raised when the TTS worker can no longer accept sentences."""
    pass


class Brain:
    def __init__(self):
        self.model = None            # resolved from OLLAMA_MODELS at first use
        self.history = []            # [(role, text)] — trimmed on every call

    # ------------------------------------------------------------ plumbing ----
    def _resolve_model(self):
        """Pick the first available model from the fallback chain."""
        if self.model:
            return self.model
        try:
            tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5).json()
            available = {m["name"] for m in tags.get("models", [])}
        except Exception:
            return None
        for candidate in config.OLLAMA_MODELS:
            if candidate in available:
                self.model = candidate
                return candidate
        return None

    def _messages(self, user_text):
        messages = [{"role": "system", "content": config.NOVA_SYSTEM_PROMPT}]
        for role, text in self.history[-config.OLLAMA_HISTORY_TURNS:]:
            messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": user_text})
        return messages

    # ---------------------------------------------------------------- public ----
    def think(self, user_text: str) -> str:
        """
        Send text to Qwen and return NOVA's full reply, in persona.
        For spoken replies prefer think_stream() — it calls on_sentence()
        as each sentence is generated, so the voice starts in ~1-2s.
        """
        return self._stream_reply(user_text, None)

    def think_stream(self, user_text: str, on_sentence) -> str:
        """Like think(), but calls on_sentence(fragment) as sentences arrive."""
        return self._stream_reply(user_text, on_sentence)

    def _stream_reply(self, user_text: str, on_sentence):
        model = self._resolve_model()
        if model is None:
            return (
                "I'm afraid my mind is offline at the moment, sir — "
                "start Ollama and I'll be myself again."
            )

        self.history.append(("user", user_text))
        state.set_status("thinking", "Thinking...")
        try:
            full = self._generate(user_text, model, on_sentence)
        except Exception:
            self.history.pop()  # drop the unanswered turn
            state.set_status("idle", "NOVA is ready")
            return "The local model didn't respond in time, sir. Shall I try again?"

        reply = _THINK_RE.sub("", full).strip()
        self.history.append(("assistant", reply))
        state.set_status("idle", "NOVA is ready")
        return reply or "I have nothing useful to add, I'm afraid."

    def _generate(self, user_text: str, model, on_sentence) -> str:
        """
        One streaming Ollama call; returns the full reply text. Streams
        NDJSON chunks, cleans them, and emits complete sentences through
        on_sentence as soon as they exist. If on_sentence dies (TTS
        worker gone), generation is abandoned early.
        """
        parts = []
        spoken_pending = ""
        try:
            with requests.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={
                    "model": model,
                    "messages": self._messages(user_text),
                    "stream": True,
                    "think": False,        # qwen3: skip hidden reasoning -> faster
                    "keep_alive": "30m",   # stay in RAM — never reload per command
                    "options": {"num_predict": 120},
                },
                stream=True,
                timeout=config.OLLAMA_TIMEOUT,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        parts.append(piece)
                        if on_sentence:
                            spoken_pending = self._emit_sentences(
                                spoken_pending + piece, on_sentence
                            )
                    if chunk.get("done"):
                        break
        except _StreamDead:
            # Voice worker is gone — stop generating to save CPU; the text
            # produced so far still reaches the UI.
            return "".join(parts)

        if on_sentence and spoken_pending.strip():
            self._emit_flush(spoken_pending, on_sentence)
        return "".join(parts)

    @staticmethod
    def _clean(fragment: str) -> str:
        text = _THINK_RE.sub("", fragment)
        text = _THINK_OPEN_RE.sub("", text)  # an unclosed <think> still streaming
        return _MD_RE.sub("", text)

    @staticmethod
    def _emit_sentences(pending: str, on_sentence) -> str:
        """Emit every complete sentence in `pending`; return the leftover tail."""
        text = Brain._clean(pending)
        m = re.search(r"^(.*[.!?…])(\s+|$)", text, re.S)
        if not m:
            return text  # no sentence boundary yet — keep buffering
        for sentence in re.findall(r"[^.!?…]+[.!?…]+", text):
            s = sentence.strip()
            if s:
                try:
                    on_sentence(s)
                except Exception:
                    raise _StreamDead()
        return text[m.end(1):].lstrip()

    @staticmethod
    def _emit_flush(tail: str, on_sentence):
        s = Brain._clean(tail).strip()
        if s:
            try:
                on_sentence(s)
            except Exception:
                raise _StreamDead()

    def warm_up(self):
        """Load the model into RAM once at startup so the first real reply is fast."""
        model = self._resolve_model()
        if model is None:
            return
        try:
            requests.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "."}],
                    "stream": False,
                    "think": False,
                    "keep_alive": "30m",
                    "options": {"num_predict": 1},
                },
                timeout=300,
            )
        except Exception:
            pass


brain = Brain()
