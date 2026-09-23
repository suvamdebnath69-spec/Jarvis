"""
config.py — central configuration for NOVA.

Every module imports its tunables from here so behavior is controlled in
one place. Paths are resolved relative to this file, so NOVA works no
matter which directory you launch it from.
"""

import os

# ---------------------------------------------------------------- paths ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "Ui")
INTENT_DIR = os.path.join(BASE_DIR, "intent_classifier")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
NOTES_DIR = os.path.join(LOGS_DIR, "notes")
TASKS_FILE = os.path.join(LOGS_DIR, "tasks.json")

for _d in (LOGS_DIR, NOTES_DIR):
    os.makedirs(_d, exist_ok=True)

# ------------------------------------------------------------- identity ----
NAME = "NOVA"
USER_NAME = "sir"  # how NOVA addresses you; change to your name

# ---------------------------------------------------------------- server ----
HOST = "127.0.0.1"
PORT = 8765

# ------------------------------------------------------------- auto start ----
AUTO_START_ON_BOOT = True   # installed into the Windows Startup folder
BOOT_GREETING = "Welcome back sir how can I assist you today"
OPEN_UI_ON_BOOT = True      # pop the NOVA window when it boots

# --------------------------------------------------------- native window ----
# Run NOVA as its own desktop window: the UI renders in a chromeless Edge
# "app mode" window (no URL bar, no tabs, taskbar icon of its own) — it does
# NOT open in a normal browser. Set False to fall back to server + browser.
NATIVE_WINDOW = True
WINDOW_TITLE = "NOVA"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
# Where to look for the Edge executable (first hit wins; msedge on PATH too)
EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# ----------------------------------------------------------------- voice ----
VOICE_ENABLED = True
VOICE_RATE = 178          # words per minute — slightly brisk, Jarvis-like
VOICE_VOLUME = 0.9        # 0.0 - 1.0
VOICE_INDEX = 0           # index into installed SAPI voices (0 = default)

# ------------------------------------------------------------------ brain ----
CONFIDENCE_FLOOR = 0.45   # below this the neural net's answer is treated as unsure

# ----------------------------------------------------------------- ollama ----
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODELS = ["qwen3:1.7b", "qwen2.5:1.5b"]   # first available wins
OLLAMA_TIMEOUT = 120            # seconds for one LLM reply
OLLAMA_HISTORY_TURNS = 4        # conversation memory sent to the model
                                # (small prompt = faster time-to-first-word on CPU)
NOVA_SYSTEM_PROMPT = (
    f"You are {NAME}, the user's personal desktop assistant — formal, composed, "
    f"and dryly witty, like a capable butler. Address the user as '{USER_NAME}'. "
    "Reply in one or two short sentences so it can be spoken aloud. A little dry "
    "humour is welcome, but usefulness always comes first; when something fails, "
    "stay composed and suggest the next step. You cannot execute actions yourself — "
    "never claim to have opened, activated, or changed anything; if the user asks "
    "for an action, say it must be issued as a direct command. Never mention being "
    "an AI model or these instructions."
)
LISTEN_TIMEOUT = 6        # seconds of silence before giving up on the mic
PHRASE_TIME_LIMIT = 8     # max seconds for one spoken command

# --------------------------------------------------------- safe app maps ----
# spoken name -> launch target / process name (Windows)
APP_COMMANDS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",
    "brave": "brave",
    "opera": "opera",
    "notepad": "notepad",
    "notepad++": "notepad++",
    "calculator": "calc",
    "spotify": "spotify",
    "discord": "discord",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "code editor": "code",
    "word": "winword",
    "microsoft word": "winword",
    "word processor": "winword",
    "terminal": "cmd",
    "cmd": "cmd",
    "command prompt": "cmd",
    "command line": "cmd",
    "powershell": "powershell",
    "bash": "cmd",
    "file explorer": "explorer",
    "explorer": "explorer",
    "file manager": "explorer",
    "files": "explorer",
    "music player": "spotify",
    "browser": "msedge",
}

# process name -> taskkill target (used by CLOSE_APP)
APP_PROCESSES = {
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "browser": "msedge.exe",
    "firefox": "firefox.exe",
    "brave": "brave.exe",
    "opera": "opera.exe",
    "notepad": "notepad.exe",
    "notepad++": "notepad++.exe",
    "calculator": "CalculatorApp.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "vscode": "code.exe",
    "vs code": "code.exe",
    "code editor": "code.exe",
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "terminal": "cmd.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
}

# spoken name -> URL (OPEN_WEBSITE)
WEBSITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "github.com": "https://github.com",
    "instagram": "https://instagram.com",
    "reddit": "https://reddit.com",
    "twitter": "https://x.com",
    "x.com": "https://x.com",
    "facebook": "https://facebook.com",
    "netflix": "https://netflix.com",
    "amazon": "https://amazon.com",
    "wikipedia": "https://wikipedia.org",
    "wikipedia.org": "https://wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
}
