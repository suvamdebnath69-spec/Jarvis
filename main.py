"""
main.py — NOVA's spine.

Wires the whole assistant together:

    input (typed in the UI, or spoken through the mic)
      -> core/fast_path  (rules + the trained neural classifier)
           -> instant action via the action layer  (common commands, no LLM lag)
           -> core/brain (Ollama + Qwen) for conversation and reasoning
      -> response spoken through TTS and shown in the UI

Run:  python main.py     -> NOVA opens as its own desktop window
      (set NATIVE_WINDOW=False in config.py for server + browser mode)
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

import requests
from flask import Flask, jsonify, request, send_from_directory

import config

# Running under pythonw (auto-start) there is no console: sys.stdout/stderr
# are None and any print() would crash NOVA. Route them to a log instead.
if sys.stdout is None or sys.stderr is None:
    _boot_log = open(
        os.path.join(config.LOGS_DIR, "nova_stdout.log"), "a", encoding="utf-8", buffering=1
    )
    sys.stdout = sys.stdout or _boot_log
    sys.stderr = sys.stderr or _boot_log
elif hasattr(sys.stdout, "isatty") and not sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
    # detached/redirected: keep logs current instead of block-buffered
    # (skip exotic buffers — e.g. test harnesses — that lack reconfigure)
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
from actions import beast_tools, calculator, documents, files, media, registry, safe_tools, system, web
from core import hotkey, stt
from core.brain import brain
from core.fast_path import fast_path
from core.scheduler import scheduler
from core.state import state
from core.tts import voice as tts

app = Flask(__name__, static_folder=config.UI_DIR, static_url_path="")


# ------------------------------------------------------------- core loop ----
def _parse_delay(text: str) -> float:
    """'remind me to eat in 10 minutes' -> 600.0 seconds. Defaults to 30 min."""
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|h\b)", text, re.I
    )
    if not m:
        return 30 * 60
    value = float(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith(("h", "hour")):
        return value * 3600
    if unit.startswith(("s", "sec")):
        return value
    return value * 60


def _schedule_reminder(text: str, params: dict) -> str:
    task = (params.get("task") or text).strip()
    task = re.sub(
        r"^(?:please\s+)?(?:can you\s+)?(?:remind me(?: to| about)?|set (?:a|an) reminder(?: for| to| about)?)\s+",
        "", task, flags=re.I,
    ).strip(" .!")
    delay = _parse_delay(text)
    when = time.time() + delay
    scheduler.add_reminder(when, task)
    if delay >= 3600:
        return f"Very well, sir. I'll remind you to {task} at {time.strftime('%H:%M', time.localtime(when))}."
    if delay >= 60:
        return f"Very well, sir. I'll remind you to {task} in {int(delay // 60)} minutes."
    return f"Very well, sir. I'll remind you to {task} shortly."


def _research_document(topic: str) -> str:
    """
    Real research: fetch the topic's material from the web, then compose
    it into a document (docx, falling back to txt) in logs/notes.
    """
    if not topic.strip():
        return "Research what, sir? Give me a topic."
    material = web.research(topic)
    if material.startswith(("The web page didn't", "Web extraction", "That page gave")):
        return material
    title = f"research_{re.sub(r'[^a-z0-9]+', '_', topic.lower()).strip('_')[:40]}"
    body = (
        f"Research document: {topic}\n"
        f"Compiled by NOVA on {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"{'=' * 60}\n\n{material}\n"
    )
    result = documents.write_document(title, body, fmt="docx")
    if "pip install" in result:  # python-docx missing — txt fallback
        result = documents.write_document(title, body, fmt="txt")
    return f"Research complete on {topic}. {result}"


def handle_command(text: str) -> dict:
    """The whole assistant in one function: understand -> act -> speak."""
    text = (text or "").strip()
    if not text:
        reply = "I didn't quite catch that, sir."
        state.add_message("nova", reply)
        return {"reply": reply, "intent": None}

    state.add_message("user", text)

    # A question-shaped input ("why is...", "how does...") is conversation,
    # not a command — route it to the brain no matter what the neural net
    # guesses. This killed a bug where "why is the sky blue" hit GET_TIME.
    if re.search(
        r"^(why|how|what do you|what's your|whats your|tell me (about|your|why|how))\b",
        text, re.I,
    ) and not re.match(r"^what(?:'s| is)? the time\b", text, re.I):
        intent, params, conf, source = "CHAT", {}, 0.0, "rule"
    else:
        u = fast_path.understand(text)
        intent, params = u["intent"], u["params"]
        conf, source = u["confidence"], u["source"]

    # ------------------------------------------ pending confirmations ----
    # A 'confirm'/'cancel' only means something while a dangerous action
    # is pending — otherwise 'yes' is conversation, never an execution.
    if intent not in ("CONFIRM", "CANCEL"):
        pending = registry.peek_pending()
        if pending and registry.is_cancel(text):
            registry.cancel_pending()
            reply = f"Very well, sir — the {pending.get('desc', pending.get('name', 'action'))} is cancelled."
            state.add_message("nova", reply, intent="CANCEL")
            tts.say(reply)
            registry.log_route(text, "CANCEL", conf, source, "local")
            return {"reply": reply, "intent": "CANCEL", "source": source}
    if intent == "CONFIRM":
        job = registry.consume_pending()
        if not job:
            reply = "There's nothing pending my confirmation, sir."
        elif "path" in job:  # a file delete
            reply = files.execute_delete(job["path"])
        else:                 # a power action
            reply = system.execute_power(job["kind"])
        state.add_message("nova", reply, intent="CONFIRM")
        tts.say(reply)
        registry.log_route(text, "CONFIRM", conf, source, "local")
        return {"reply": reply, "intent": "CONFIRM", "source": source}
    if intent == "CANCEL":
        registry.cancel_pending()
        reply = "Cancelled, sir."
        state.add_message("nova", reply, intent="CANCEL")
        tts.say(reply)
        registry.log_route(text, "CANCEL", conf, source, "local")
        return {"reply": reply, "intent": "CANCEL", "source": source}

    # Conversation, reasoning, or anything the fast path is unsure of -> Qwen
    if intent in (None, "CHAT") or conf < config.CONFIDENCE_FLOOR:
        if re.search(r"\bbeast\b", text, re.I):
            # Beast-adjacent but not the exact keyword: never let the LLM
            # pretend it armed anything — state the real command instead.
            reply = (
                "Beast Mode is engaged with the command 'enter beast mode', sir — "
                "and 'stand down' returns me to normal duty."
            )
            state.add_message("nova", reply, intent="CHAT")
            tts.say(reply)
            registry.log_route(text, "BEAST_HINT", conf, source, "local")
            return {"reply": reply, "intent": "CHAT", "source": "rule"}

        # Stream the reply sentence-by-sentence: the voice starts as soon
        # as the first complete sentence exists instead of after the whole
        # reply finishes generating.
        spoken = {"n": 0}

        def _speak_piece(sentence: str):
            spoken["n"] += 1
            tts.say(sentence)

        full_reply = brain.think_stream(text, _speak_piece)
        state.add_message("nova", full_reply, intent="CHAT")
        if spoken["n"] == 0:
            # Nothing streamed (offline/degraded path) — speak it whole now.
            tts.say(full_reply)
        registry.log_route(text, "CHAT", conf, source, "llm", used_llm=True)
        return {"reply": full_reply, "intent": "CHAT", "source": "llm"}

    # ------------------------------------------------------ action layer ----
    route = "local"
    used_web = False
    try:
        reply = _dispatch(intent, text, params)
    except Exception as e:
        reply = f"That action didn't go through, sir — I've logged it."
        route = "error"
        registry.log_route(text, intent, conf, source, route, error=str(e))
    else:
        registry.log_route(text, intent, conf, source, route, used_web=used_web)

    state.add_message("nova", reply, intent=intent)
    tts.say(reply)
    return {"reply": reply, "intent": intent, "source": source, "confidence": round(conf, 3), "route": route}


def _dispatch(intent: str, text: str, params: dict) -> str:
    """The action registry: intent -> local handler. One line per capability."""
    if intent == "OPEN_APP":
        return safe_tools.open_app(params.get("app", ""))
    if intent == "CLOSE_APP":
        return safe_tools.close_app(params.get("app", ""))
    if intent == "OPEN_WEBSITE":
        if params.get("private"):
            return web.open_website_incognito(params.get("site", ""))
        return web.open_website(params.get("site", ""))
    if intent == "RESEARCH":
        return _research_document(params.get("topic", ""))
    if intent == "CLICK_AT":
        if not state.beast_armed():
            return "Clicking the screen is a Beast Mode skill, sir — 'enter beast mode' first."
        return beast_tools.click_window(
            int(params.get("x", 0)), int(params.get("y", 0)), params.get("label", "")
        )
    if intent == "TYPE_TEXT":
        if not state.beast_armed():
            return "Typing for you is a Beast Mode skill, sir — 'enter beast mode' first."
        body = params.get("body", "").strip().strip('"').strip("'")
        return beast_tools.type_text(body, press_enter=False)
    if intent == "INSTAGRAM_DM":
        if not state.beast_armed():
            return "Messaging is a Beast Mode skill, sir — 'enter beast mode' first."
        return beast_tools.dm_instagram(
            params.get("user", ""), params.get("msg", "Hi").strip().strip('"').strip("'")
        )
    if intent == "SEARCH_WEB":
        return web.search_web(params.get("query") or text)
    if intent == "OPEN_TAB":
        return web.open_tab()
    if intent == "CLOSE_TAB":
        return web.close_tab()
    if intent == "SCROLL":
        return web.scroll(_scroll_direction(text))
    if intent == "REMINDER":
        return _schedule_reminder(text, params)
    if intent == "LIST_REMINDERS":
        return files.show_reminders(state)
    if intent == "TAKE_NOTE":
        body = (params.get("body") or text).strip()
        return documents.take_note(body[:40] or "quick note", body)
    if intent == "READ_NOTES":
        return documents.list_notes()
    if intent == "GET_TIME":
        return safe_tools.get_time()
    if intent == "GET_DATE":
        return system.get_date()
    if intent == "GET_DAY":
        return system.get_day()
    if intent == "CALCULATE":
        return calculator.calculate(text)
    if intent == "SET_VOLUME":
        m = re.search(r"(\d+)", text)
        return system.set_volume(int(m.group(1))) if m else "What level, sir?"
    if intent == "VOLUME_UP":
        return system.volume_up()
    if intent == "VOLUME_DOWN":
        return system.volume_down()
    if intent == "MUTE":
        return system.mute()
    if intent == "UNMUTE":
        return system.mute(unmute=True)
    if intent == "GET_VOLUME":
        return system.get_volume()
    if intent == "BRIGHTNESS_UP":
        return system.brightness_up()
    if intent == "BRIGHTNESS_DOWN":
        return system.brightness_down()
    if intent == "SET_BRIGHTNESS":
        m = re.search(r"(\d+)", text)
        return system.set_brightness(int(m.group(1))) if m else "What level, sir?"
    if intent == "BATTERY_STATUS":
        return system.battery_status()
    if intent == "WIFI_STATUS":
        return system.wifi_status()
    if intent == "SCREENSHOT":
        return system.take_screenshot()
    if intent == "LOCK_SCREEN":
        return system.lock_screen()
    if intent == "PLAY_MUSIC":
        return media.play_music()
    if intent == "PAUSE_MUSIC":
        return media.pause_music()
    if intent == "NEXT_TRACK":
        return media.next_track()
    if intent == "PREV_TRACK":
        return media.prev_track()
    if intent == "CREATE_FOLDER":
        name = (params.get("name") or params.get("name2") or "").strip()
        where = (params.get("where3") or "Desktop").strip().capitalize()
        if not name:  # e.g. "make a new folder on desktop" — name it by location
            name = "New Folder"
        return files.create_folder(name, where)
    if intent == "CREATE_FILE":
        return files.create_text_file((params.get("name") or "").strip())
    if intent == "OPEN_FOLDER":
        return files.open_folder(params.get("where", ""))
    if intent == "LIST_FOLDER":
        return files.list_folder(params.get("where") or params.get("where2") or "downloads")
    if intent == "FIND_FILES":
        pattern = (params.get("pat") or params.get("pat2") or params.get("pat3") or "").strip()
        where = (params.get("where") or params.get("where2") or "documents").strip()
        # "find X files" without a folder -> search Documents
        where = where if where in ("desktop", "documents", "downloads", "notes") else "documents"
        return files.find_files(pattern, where)
    if intent == "RENAME_FILE":
        return files.rename_file(
            (params.get("old") or "").strip(), (params.get("new") or "").strip(),
            (params.get("where") or "Desktop").strip(),
        )
    if intent == "MOVE_FILE":
        return files.move_file((params.get("name") or "").strip(), params.get("dest", ""))
    if intent == "DELETE_FILE":
        descriptor, note = files.request_delete(
            (params.get("name") or "").strip(), (params.get("where") or "Desktop").strip()
        )
        if descriptor is None:
            return note
        registry.set_pending_delete(descriptor)
        return (
            f"Deleting '{descriptor['name']}' is irreversible, sir — "
            "shall I proceed? Say confirm or cancel."
        )
    if intent == "LIST_TASKS":
        return files.show_tasks()
    if intent == "SHUTDOWN":
        job = system.request_power("shutdown")
        registry.set_pending(job["kind"], "shutdown")
        return "Shutting down the PC, sir — this I must confirm. Say confirm or cancel."
    if intent == "RESTART":
        job = system.request_power("restart")
        registry.set_pending(job["kind"], "restart")
        return "Restarting the PC, sir — confirm, or cancel?"
    if intent == "SLEEP_PC":
        job = system.request_power("sleep")
        registry.set_pending(job["kind"], "sleep")
        return "Putting the PC to sleep, sir — confirm, or cancel?"
    if intent == "BEAST_ON":
        state.set_beast_mode(True)
        beast_tools.log_action("BEAST_MODE", "armed by command")
        return "Beast Mode armed, sir. Expanded tool access is live — do be careful with it."
    if intent == "BEAST_OFF":
        state.set_beast_mode(False)
        beast_tools.log_action("BEAST_MODE", "disarmed by command")
        return "Standing down. Beast Mode is disengaged."
    # Anything not registered — the butler reasons it out.
    return brain.think(text)


def _scroll_direction(text: str) -> str:
    t = (text or "").lower()
    if "top" in t or "upmost" in t or "beginning" in t:
        return "top"
    if "bottom" in t or "end" in t:
        return "bottom"
    if re.search(r"\bup\b", t):
        return "up"
    return "down"


# ---------------------------------------------------------------- server ----
@app.route("/")
def index():
    return send_from_directory(config.UI_DIR, "Index.html")


@app.route("/beast")
def beast():
    return send_from_directory(config.UI_DIR, "Beast.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(config.UI_DIR, filename)


@app.route("/api/command", methods=["POST"])
def api_command():
    data = request.get_json(silent=True) or {}
    return jsonify(handle_command(data.get("text", "")))


@app.route("/api/listen", methods=["POST"])
def api_listen():
    transcript, error = stt.listen()
    if error:
        return jsonify({"reply": error, "intent": None, "error": True})
    result = handle_command(transcript)
    result["transcript"] = transcript
    return jsonify(result)


@app.route("/api/state")
def api_state():
    status, detail = state.get_status()
    return jsonify(
        {
            "status": status,
            "detail": detail,
            "tasks": state.get_tasks(),
            "stats": state.get_stats(),
            "beast_mode": state.beast_armed(),
            "voice": state.voice_on(),
        }
    )


@app.route("/api/history")
def api_history():
    limit = request.args.get("limit", 40, type=int)
    return jsonify({"messages": state.get_history(limit)})


@app.route("/api/announcements")
def api_announcements():
    since = request.args.get("since", 0, type=int)
    items, last_id = state.announcements_since(since)
    return jsonify({"announcements": items, "last_id": last_id})


@app.route("/api/voice", methods=["POST"])
def api_voice():
    data = request.get_json(silent=True) or {}
    state.set_voice_enabled(bool(data.get("enabled", True)))
    return jsonify({"voice": state.voice_on()})


@app.route("/api/beast", methods=["POST"])
def api_beast():
    data = request.get_json(silent=True) or {}
    state.set_beast_mode(bool(data.get("enabled", False)))
    beast_tools.log_action("BEAST_MODE", "armed" if state.beast_armed() else "disarmed")
    return jsonify({"beast_mode": state.beast_armed()})


@app.route("/api/focus", methods=["POST"])
def api_focus():
    """Ask the running instance to surface its window."""
    _open_ui()
    return jsonify({"focused": True})


# ------------------------------------------------------------ background ----
def _stats_loop():
    while True:
        try:
            safe_tools.system_stats()
        except Exception:
            pass
        time.sleep(3)


def _warm_brain():
    try:
        brain.warm_up()
    except Exception:
        pass


# ------------------------------------------------------------ auto start ----
def _port_open(host, port) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _ensure_ollama() -> bool:
    """If Ollama isn't running after boot, bring it up ourselves."""

    def up() -> bool:
        try:
            return requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).status_code == 200
        except Exception:
            return False

    if up():
        return True
    exe = shutil.which("ollama")
    if exe is None:
        print("Ollama not found — the brain stays offline until it starts.")
        return False
    try:
        subprocess.Popen(
            [exe, "serve"],
            creationflags=0x00000008 | 0x00000200,  # DETACHED | below-normal
            stdout=open(os.path.join(config.LOGS_DIR, "ollama.log"), "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
    except Exception:
        return False
    for _ in range(20):
        if up():
            print("Ollama was down — started it for the brain.")
            return True
        time.sleep(1)
    print("Ollama did not come up in time — brain offline for now.")
    return False


def _greet():
    """NOVA's boot greeting — spoken and shown, as fast as the engine allows."""
    time.sleep(0.6)  # brief settle for the audio device
    hour = time.localtime().tm_hour
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    greeting = f"Good {part}, sir. {config.BOOT_GREETING}"
    state.add_announcement(greeting)
    state.add_message("nova", greeting)
    tts.say(greeting)


def _open_browser():
    """Last-resort UI surface — only used when windowed mode is off/unavailable."""
    subprocess.Popen(
        ["cmd", "/c", "start", "", f"http://{config.HOST}:{config.PORT}"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _open_ui():
    """
    Surface NOVA for the user. In windowed mode (the default), this ALWAYS
    goes to NOVA's own desktop window — re-issuing the same Edge app
    command focuses the existing window (Edge is single-instance per
    profile+URL), never a normal browser tab.
    """
    if config.NATIVE_WINDOW:
        if _find_edge():
            _run_windowed()
        else:
            print("Edge not found — cannot open the desktop window; NOVA keeps running.")
        return
    _open_browser()


def _on_hotkey():
    print("Ctrl+J pressed — opening NOVA's UI.")
    _open_ui()


def _serve():
    app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False)


def _find_edge():
    exe = shutil.which("msedge")
    if exe:
        return exe
    for path in config.EDGE_PATHS:
        if os.path.exists(path):
            return path
    return None


def _run_windowed():
    """
    Open NOVA as its own desktop window via Edge's --app mode: chromeless,
    no URL bar, no tabs, its own taskbar icon — not a browser session.
    Re-launching the same app URL/profile focuses the existing window
    instead of opening a duplicate, so Ctrl+J-style warm starts just work.
    """
    exe = _find_edge()
    if exe is None:
        print("Edge not found — desktop window unavailable; NOVA keeps running.")
        return
    profile = os.path.join(config.LOGS_DIR, "nova_window_profile")
    try:
        subprocess.Popen(
            [
                exe,
                f"--app=http://{config.HOST}:{config.PORT}",
                f"--user-data-dir={profile}",
                f"--window-size={config.WINDOW_WIDTH},{config.WINDOW_HEIGHT}",
                "--no-first-run",
            ],
            creationflags=0x00000008 | 0x00000200,  # DETACHED | below-normal
        )
        print("NOVA running as its own desktop window (Edge app mode) — no browser.")
    except Exception as e:
        print(f"Desktop window failed ({e}) — NOVA keeps running; retry with Ctrl+J.")


def main():
    if _port_open(config.HOST, config.PORT):
        # Ctrl+J (or a double-click) while NOVA is already running lands
        # here: don't start a second brain, just surface the UI.
        print("NOVA is already running — opening its UI.")
        _open_ui()
        return

    _ensure_ollama()
    scheduler.start()
    threading.Thread(target=_stats_loop, daemon=True).start()
    threading.Thread(target=_warm_brain, daemon=True).start()
    threading.Thread(target=_greet, daemon=True).start()
    # In windowed mode the window shows itself; the browser pop-up is
    # only for plain-server mode.
    if config.OPEN_UI_ON_BOOT and os.environ.get("NOVA_AUTOSTART") == "1" and not config.NATIVE_WINDOW:
        threading.Thread(target=_open_ui, daemon=True).start()
    hotkey.start_hotkey(_on_hotkey)
    print(f"NOVA online -> http://{config.HOST}:{config.PORT}   (beast mode: /beast)")

    if config.NATIVE_WINDOW:
        # Flask serves from a background thread; the desktop window is a
        # separate Edge app-mode process, so the main thread just idles.
        threading.Thread(target=_serve, daemon=True).start()
        for _ in range(50):
            if _port_open(config.HOST, config.PORT):
                break
            time.sleep(0.1)
        _run_windowed()
        while True:  # keep the brain, scheduler and hotkey alive
            time.sleep(3600)
    else:
        app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
