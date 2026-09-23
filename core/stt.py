"""
stt.py — NOVA's ears.

One-shot microphone listening with the SpeechRecognition stack. The mic
button in the UI calls listen(); NOVA calibrates for ambient noise, waits
for speech, and returns the transcript. Google's free recognizer is used
because it handles noisy home-mic audio well; errors degrade gracefully.
"""

import speech_recognition as sr

import config
from core.state import state


def listen():
    """
    Listen once and return (transcript, error).
    On success error is None. On failure transcript is "" and error holds
    a human-readable reason (no mic, silence, no internet, ...).
    """
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            state.set_status("listening", "Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            try:
                audio = recognizer.listen(
                    source,
                    timeout=config.LISTEN_TIMEOUT,
                    phrase_time_limit=config.PHRASE_TIME_LIMIT,
                )
            except Exception:
                state.set_status("idle", "NOVA is ready")
                return "", "I didn't catch anything — try again."

        state.set_status("thinking", "Understanding...")
        try:
            transcript = recognizer.recognize_google(audio).strip()
            return transcript, None
        except sr.UnknownValueError:
            return "", "I heard you, but couldn't make out the words."
        except sr.RequestError:
            return "", "Speech service unreachable — check your internet."
    except Exception:
        state.set_status("idle", "NOVA is ready")
        return "", "No microphone available on this machine."
