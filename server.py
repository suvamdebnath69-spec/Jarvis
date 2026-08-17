"""Jarvis web server - serves the HUD and streams chat from the brain.

The heavy lifting (model, research, persona) lives in brain.py; this file is
just the HTTP layer.

Usage:
  python server.py                Run the server (opens the HUD in your browser)
  python server.py --no-browser   Run without opening a tab
  python server.py --port 8420    Serve on a different port
  python server.py --no-research  Never research the web
  python server.py --model NAME   Use a specific Ollama model
  python server.py --install      Auto-start at Windows login
  python server.py --remove       Remove auto-start
"""

import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

import brain

PORT = 8420
HOST = "127.0.0.1"
RESEARCH = True  # set False via --no-research

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
LOG_PATH = os.path.join(BASE_DIR, "jarvis_web.log")

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


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open(INDEX_PATH, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, {"error": "index.html missing"})
        elif self.path == "/api/ping":
            self._send(200, {"ok": True})   # fast liveness check (no Ollama)
        elif self.path == "/api/health":
            model, models = brain.active_model()
            self._send(200, {
                "ok": model is not None,
                "model": model or brain.LOCAL_MODEL,
                "models": models,
                "ollama": bool(models),
            })
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/chat":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "bad request"})
            return

        messages = payload.get("messages", [])[-brain.MAX_HISTORY:]
        research = payload.get("research", True) and RESEARCH

        results = []
        augmented = False
        llm_messages = [{"role": "system", "content": brain.build_system_prompt()}]
        # Clean the latest question like the voice assistant does (STT fixes,
        # abbreviation expansion like "BND" -> "Brand New Day").
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                messages[i] = dict(messages[i], content=brain.expand_entities(
                    brain.clean_stt(messages[i]["content"])))
                break
        if research:
            last_user = next((m["content"] for m in reversed(messages)
                              if m.get("role") == "user"), "")
            if last_user and brain.needs_web(last_user):
                log(f"researching: {last_user[:60]}")
                results = brain.web_search(last_user[:brain.MAX_QUERY])
                if results:
                    aug = brain.augmented_question(last_user, results)
                    llm_messages += messages[:-1]
                    llm_messages.append({"role": "user", "content": aug})
                    augmented = True
            elif last_user:
                log("no web needed (conversational question)")
        if not augmented:
            llm_messages += messages

        # Stream the reply back as NDJSON so the HUD fills in progressively
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(obj):
            self.wfile.write((json.dumps(obj) + "\n").encode())

        try:
            for delta in brain.stream_chat(llm_messages):
                if delta:
                    emit({"delta": delta})
            emit({"done": True,
                  "research": {"sources": len(results)} if research else None})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser closed the tab mid-stream
        except Exception as e:
            log(f"/api/chat error: {e}")
            try:
                emit({"error": str(e)})
            except Exception:
                pass

    def log_message(self, *args):  # keep the console quiet
        pass


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
          "Jarvis will launch in your browser when you log in.")


def remove_startup():
    if os.path.exists(STARTUP_FILE):
        os.remove(STARTUP_FILE)
        print(f"Removed auto-start:\n  {STARTUP_FILE}")
    else:
        print("No auto-start entry found.")


def main():
    parser = argparse.ArgumentParser(description="Jarvis web interface")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-research", action="store_true",
                        help="answer from the model's own knowledge only")
    parser.add_argument("--model", help="Ollama model to use")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()

    global RESEARCH
    if args.no_research:
        RESEARCH = False
    if args.model:
        brain.LOCAL_MODEL = args.model

    if args.install:
        install_startup()
        return
    if args.remove:
        remove_startup()
        return

    url = f"http://{HOST}:{args.port}/"
    try:
        server = ThreadingHTTPServer((HOST, args.port), Handler)
    except OSError:
        # Already running (or the port is taken): just open the existing HUD
        # instead of stacking a duplicate server.
        print(f"Jarvis UI already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    log(f"Jarvis UI listening on {url} (model: {brain.LOCAL_MODEL})")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
