"""Jarvis - the headless voice assistant.

Pipeline (all local except speech-to-text):
    MIC -> STT (Google, free) -> text cleanup -> [web research if needed]
      -> local Ollama model (streaming) -> chunked neural TTS -> SPEAKER

JARVIS starts speaking as soon as the first sentence is generated, so the
time to first spoken reply is much shorter than the full answer time.

Usage:
  python assistant.py              Run in wake-word mode ("Hey Jarvis, ...")
  python assistant.py --nowake     Listen continuously, no wake word
  python assistant.py --install    Auto-start on Windows login
  python assistant.py --remove     Remove auto-start
  python assistant.py --test       Self-check mic, voice, model, and web
  python assistant.py --model NAME Use a specific Ollama model
"""

import argparse
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date

import numpy as np
import requests
import sounddevice as sd
import speech_recognition as sr

from brain import (LOCAL_MODEL, MAX_HISTORY, active_model, build_messages,
                   build_system_prompt, chat, clean_stt, ensure_sir,
                   expand_entities, format_context, maybe_clarify, needs_web,
                   ollama_models, stream_chat, web_search)
from voice import StreamingVoice

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NAME = "jarvis"                                     # wake-word name
WAKE_PHRASES = ["hey " + NAME, "okay " + NAME, "hey assistant", NAME]
SAMPLE_RATE = 16000
PHRASE_LIMIT = 7.0
TAIL_SILENCE = 1.6
HISTORY_TURNS = int(os.environ.get("JARVIS_HISTORY", "8"))  # rolling window
WAKE_HOTKEY = os.environ.get("JARVIS_HOTKEY", "ctrl+alt+j")  # keyboard wake

# Optional global keyboard wake: press the hotkey, then just say your command.
try:
    import keyboard as _kb
    HOTKEY_OK = True
except Exception:
    _kb = None
    HOTKEY_OK = False
_hotkey_pressed = threading.Event()


def init_hotkey():
    """Arm the global keyboard wake. No-op if the keyboard lib is missing."""
    if _kb is None or not WAKE_HOTKEY:
        return False
    try:
        _kb.add_hotkey(WAKE_HOTKEY, _hotkey_pressed.set)
        log(f"keyboard wake armed: {WAKE_HOTKEY}")
        return True
    except Exception as e:
        log(f"keyboard wake unavailable: {e}")
        return False


WEB_URL = "http://127.0.0.1:8420"
WEB_PING = WEB_URL + "/api/ping"   # instant liveness check (no Ollama)


def web_ui_running():
    try:
        return requests.get(WEB_PING, timeout=2).ok
    except Exception:
        return False


def launch_web_ui():
    """Start the HUD server if it isn't up, then open it in the browser."""
    if not web_ui_running():
        py = sys.executable
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else py
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "server.py")
        log("starting web interface...")
        try:
            subprocess.Popen([exe, script, "--no-browser"],
                             creationflags=getattr(subprocess,
                                                   "CREATE_NO_WINDOW", 0))
        except Exception as e:
            log(f"failed to start web interface: {e}")
        for _ in range(20):                       # wait up to ~10s for boot
            time.sleep(0.5)
            if web_ui_running():
                break
    if web_ui_running():
        webbrowser.open(WEB_URL + "/")
        log("web interface opened in browser")
        return True
    log("web interface failed to start")
    return False

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assistant.log")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
STARTUP_FILE = os.path.join(STARTUP_DIR, "jarvis_startup.vbs")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Speech input
# ---------------------------------------------------------------------------
def capture_audio(timeout=PHRASE_LIMIT):
    """Record from the default mic until speech + tail silence or timeout."""
    block = int(SAMPLE_RATE * 0.1)
    frames = bytearray()
    ambient_blocks = 0
    ambient_max = 0.0
    silence_blocks = 0
    max_silence_blocks = int(TAIL_SILENCE / 0.1)
    heard = False
    start = time.monotonic()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        while time.monotonic() - start < timeout:
            if _hotkey_pressed.is_set():        # keyboard wake pressed: abort now
                return None, False
            data, _ = stream.read(block)
            arr = np.frombuffer(data, dtype=np.int16)
            peak = float(np.max(np.abs(arr))) if arr.size else 0.0

            if ambient_blocks < 5:                      # learn room noise (0.5s)
                ambient_max = max(ambient_max, peak)
                ambient_blocks += 1
                continue

            threshold = max(ambient_max * 2.5, 400)
            if peak > threshold:
                heard = True
                silence_blocks = 0
            elif heard:
                silence_blocks += 1
                if silence_blocks > max_silence_blocks:
                    break

            if heard:
                frames.extend(data)

    if not heard:
        return None, False
    return sr.AudioData(bytes(frames), SAMPLE_RATE, 2), True


def recognize(audio):
    """Speech-to-text with an en-IN / en-US pass so Indian English and other
    accents get a fair shot. Uses the same audio, no repeated mic captures."""
    recognizer = sr.Recognizer()
    for lang in ("en-IN", "en-US"):
        try:
            return recognizer.recognize_google(audio, language=lang)
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            raise RuntimeError(f"Speech recognition unavailable: {e}")
    return None


def listen_for_request(nowake):
    """One full listen cycle -> cleaned request text, or None."""
    t0 = time.monotonic()
    audio, heard = capture_audio()
    if not heard:
        return None
    try:
        text = recognize(audio)
    except RuntimeError as e:
        log(f"STT error: {e}")
        return None
    if not text:
        return None
    stt_ms = (time.monotonic() - t0) * 1000
    log(f"STT ({stt_ms:.0f}ms): {text}")
    text = clean_stt(text)
    log("CLEANED: " + text)
    return extract_request(text, nowake)


def extract_request(text, nowake):
    t = text.lower().strip()
    if nowake:
        return t
    for phrase in sorted(WAKE_PHRASES, key=len, reverse=True):
        if t.startswith(phrase):
            return t[len(phrase):].strip(" ,.:;!?")
    return None


# ---------------------------------------------------------------------------
# Reply generation + chunked speech (speak while the model still generates)
# ---------------------------------------------------------------------------
SENTENCE_BOUNDARY = re.compile(r"[.!?]['\"]?\s*$")
ABBREV_END = re.compile(r"\b(mr|mrs|ms|dr|st|vs|etc|e\.?g|i\.?e|no|fig|jr)\.?$",
                        re.I)


def _is_sentence_end(buf, min_len=25):
    if len(buf) < min_len or not SENTENCE_BOUNDARY.search(buf):
        return False
    core = re.sub(r"['\"]?\s*$", "", buf).rstrip()
    if re.search(r"[.!?]", core) and ABBREV_END.search(core.rstrip(".!?")):
        return False
    return True


def reply_and_speak(request, history, voice):
    """Route to web if needed, stream the answer, and speak it chunk by chunk.

    Returns the full reply text.
    """
    t_start = time.monotonic()

    # current-information router: web only when it matters
    results = []
    if needs_web(request):
        log(f"researching: {request[:60]}")
        t_r = time.monotonic()
        try:
            results = web_search(request)
            log(f"web scan complete - {len(results)} sources "
                f"({(time.monotonic()-t_r)*1000:.0f}ms)")
        except Exception as e:
            log(f"research failed: {e}")
    else:
        log("no web needed (conversational question)")

    messages = build_messages(history, results)

    reply_parts = []
    buf = ""
    spoke_any = False
    t_first_audio = None
    try:
        for delta in stream_chat(messages):
            reply_parts.append(delta)
            buf += delta
            if _is_sentence_end(buf):
                chunk = buf.strip()
                if not spoke_any:
                    chunk = ensure_sir(chunk)
                    spoke_any = True
                voice.say(chunk)
                if t_first_audio is None:
                    t_first_audio = time.monotonic()
                    log(f"first spoken chunk queued after "
                        f"{(t_first_audio-t_start)*1000:.0f}ms")
                buf = ""
    except Exception as e:
        log(f"Ollama error: {e}")
        voice.say("I ran into a problem talking to the local model, sir. "
                  "Is Ollama still running?")
        voice.wait()
        return ""

    if buf.strip():
        chunk = buf.strip()
        if not spoke_any:
            chunk = ensure_sir(chunk)
            spoke_any = True
        voice.say(chunk)
        if t_first_audio is None:
            t_first_audio = time.monotonic()
            log(f"first spoken chunk queued after "
                f"{(t_first_audio-t_start)*1000:.0f}ms")

    full = "".join(reply_parts).strip()
    log(f"generation done after {(time.monotonic()-t_start)*1000:.0f}ms")
    voice.wait()
    log(f"speech finished after {(time.monotonic()-t_start)*1000:.0f}ms "
        f"(total)")
    return full


# ---------------------------------------------------------------------------
# Built-in spoken commands
# ---------------------------------------------------------------------------
def handle_command(text, voice):
    t = text.lower()
    if any(w in t for w in ("exit", "quit", "goodbye", "go to sleep",
                            "stop listening", "shut down")):
        voice.say("Goodbye!")
        voice.wait()
        return "quit"
    if any(w in t for w in ("what can you do", "help")):
        voice.say("I can answer questions, check the web for current "
                  f"information, and hold a conversation, sir. Say, hey "
                  f"{NAME}, and ask me anything. To make me stop, say exit.")
        voice.wait()
        return "handled"
    return None


# ---------------------------------------------------------------------------
# Windows auto-start
# ---------------------------------------------------------------------------
def _quote(p):
    return '"' + p.replace('"', '""') + '"'


def install_startup():
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else py
    script = os.path.abspath(__file__)
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.Run {_quote(exe)} & " " & {_quote(script)}, 0, False\r\n'
    )
    os.makedirs(STARTUP_DIR, exist_ok=True)
    with open(STARTUP_FILE, "w", encoding="ascii") as f:
        f.write(vbs)
    print(f"Installed auto-start:\n  {STARTUP_FILE}\n"
          "Jarvis will launch when you log in to Windows.")


def remove_startup():
    if os.path.exists(STARTUP_FILE):
        os.remove(STARTUP_FILE)
        print(f"Removed auto-start:\n  {STARTUP_FILE}")
    else:
        print("No auto-start entry found.")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def run_self_test():
    print("== Jarvis self-test ==\n")
    ok = True

    print("[1/4] Microphone ...")
    try:
        dev = sd.default.device[0]
        name = sd.query_devices(dev)["name"] if dev is not None else "(default)"
        print(f"  OK - input device: {name}")
    except Exception as e:
        print(f"  FAIL - {e}")
        ok = False

    print("[2/4] Voice (TTS) ...")
    v = StreamingVoice()
    if v._edge is not None and v._mixer is not None:
        print(f"  OK - neural voice: {v.voice}")
    else:
        print("  WARN - edge-tts unavailable, using system voice fallback")
    v.stop()

    print("[3/4] Ollama model ...")
    if requests.get("http://localhost:11434/api/version", timeout=3).ok:
        model, models = active_model()
        if model:
            print(f"  OK - using model: {model}"
                  + (f" (installed: {', '.join(models)})" if len(models) > 1 else ""))
        else:
            print("  FAIL - no models installed. Run:  ollama pull qwen2.5:1.5b")
            ok = False
    else:
        print("  FAIL - Ollama is not running (start it from your tray).")
        ok = False

    print("[4/4] Web research ...")
    try:
        res = web_search("current events today")
        print(f"  OK - {len(res)} source(s) found")
    except Exception as e:
        print(f"  FAIL - {e}")
        ok = False

    print("\n" + ("All checks passed." if ok else "Some checks failed - see above."))
    if ok:
        v = StreamingVoice()
        v.say("All systems check passed. Say, hey jarvis, and ask me anything.")
        v.wait()
        v.stop()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run(nowake):
    model, models = active_model()
    if model is None:
        print("No Ollama models installed. Run:  ollama pull qwen2.5:1.5b")
        return
    if model != LOCAL_MODEL:
        print(f"Using {model} (JARVIS_MODEL={LOCAL_MODEL} not installed)")

    voice = StreamingVoice()
    history = [{"role": "system", "content": build_system_prompt()}]

    if nowake:
        log("GREETING: Listening continuously. Say exit to stop.")
        voice.say("Listening continuously. Say exit to stop.")
    else:
        log("GREETING: Welcome back, sir! How can I help you?")
        voice.say("Welcome back, sir! How can I help you?")
    voice.wait()
    log("listening for wake word...")

    init_hotkey()

    while True:
        if _hotkey_pressed.is_set():
            _hotkey_pressed.clear()
            log(f"HOTKEY: keyboard wake ({WAKE_HOTKEY})")
            launch_web_ui()                       # pop the HUD immediately
            if not nowake:
                voice.say("Yes, sir?")
                voice.wait()
                try:
                    request = listen_for_request(nowake=True)  # or speak it
                except Exception as e:            # e.g. no mic available
                    log(f"mic unavailable: {e}")
                    request = None
            else:
                request = None
        else:
            request = listen_for_request(nowake)
        if request is None:
            continue

        # Ask before guessing on bare unknown acronyms ("BND" alone)
        clarification = maybe_clarify(request)
        if clarification:
            log(f"CLARIFY: {clarification}")
            voice.say(clarification)
            voice.wait()
            continue

        request = expand_entities(request)
        log("SENDING: " + request)

        cmd = handle_command(request, voice)
        if cmd == "quit":
            return
        if cmd == "handled":
            continue

        history.append({"role": "user", "content": request})
        history = history[-2 * HISTORY_TURNS:]

        full = reply_and_speak(request, history, voice)
        if full:
            history.append({"role": "assistant", "content": full})


def main():
    parser = argparse.ArgumentParser(description="Jarvis voice assistant")
    parser.add_argument("--nowake", action="store_true",
                        help="listen continuously without a wake word")
    parser.add_argument("--install", action="store_true",
                        help="auto-start on Windows login")
    parser.add_argument("--remove", action="store_true",
                        help="remove the auto-start entry")
    parser.add_argument("--test", action="store_true",
                        help="self-check mic, voice, model, and web")
    parser.add_argument("--model", help="Ollama model to use (overrides env)")
    args = parser.parse_args()

    if args.model:
        import brain
        brain.LOCAL_MODEL = args.model

    if args.install:
        install_startup()
    elif args.remove:
        remove_startup()
    elif args.test:
        run_self_test()
    else:
        if not requests.get("http://localhost:11434/api/version",
                            timeout=3).ok:
            print("Ollama isn't running. Start it from your tray.")
            return
        try:
            run(args.nowake)
        except KeyboardInterrupt:
            pass
        except Exception:
            import traceback
            log("Fatal error:\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
