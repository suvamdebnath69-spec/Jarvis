"""
safe_tools.py — local machine actions that are safe to run unattended.

open_app()      launch an app by spoken name
close_app()     gracefully stop an app's processes
get_time()      current date/time as a speakable sentence
system_stats()  CPU / RAM / storage / battery for the Performance panel
"""

import datetime
import os
import subprocess

import psutil

import config
from core.state import state


def open_app(name: str):
    target = config.APP_COMMANDS.get(name.lower())
    if target is None:
        return f"I don't know how to open {name} yet."
    try:
        subprocess.Popen(["cmd", "/c", "start", "", target],
                         shell=False,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return f"Opening {name}."
    except Exception:
        return f"I tried, but {name} didn't start."


def close_app(name: str):
    """
    Close an app: gentle taskkill first (lets it save), forced kill as
    fallback so NOVA never hangs on an app showing a save dialog.
    """
    process = config.APP_PROCESSES.get(name.lower())
    if process is None:
        return f"I don't know which process {name} runs as."
    if process == "explorer.exe":
        return "I won't close file explorer — that would hide your desktop."
    result = subprocess.run(
        ["taskkill", "/IM", process],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=8,
    )
    if result.returncode == 0:
        return f"Closed {name}."
    # Graceful close refused or is stuck on a dialog — force it.
    force = subprocess.run(
        ["taskkill", "/IM", process, "/F"],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=8,
    )
    if force.returncode == 0:
        return f"{name.replace('.exe', '')} was stuck, so I closed it firmly."
    return f"{name} doesn't seem to be running."


def get_time():
    now = datetime.datetime.now()
    return f"It's {now.strftime('%I:%M %p').lstrip('0')} on {now.strftime('%A, %B %d')}."


def system_stats():
    """Refresh live system stats into shared state (polled by the UI)."""
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage("C:\\").percent if os.name == "nt" else psutil.disk_usage("/").percent
    battery = None
    try:
        bat = psutil.sensors_battery()
        if bat is not None:
            battery = bat.percent
    except Exception:
        pass

    overall = round(100 - (cpu + ram + disk) / 3)
    state.set_stats(cpu=round(cpu), ram=round(ram), storage=round(disk),
                    battery=battery, overall=max(0, overall))
