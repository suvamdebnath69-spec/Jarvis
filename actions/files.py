"""
files.py — local-first file and folder operations.

All operations live inside allowlisted roots (Desktop, Documents, Downloads,
NOVA's logs/notes). Destructive actions (delete) return a pending-confirmation
descriptor instead of executing — main.py's confirmation flow decides.

NEVER runs arbitrary shell commands, and never accepts paths from the LLM.
"""

import os
import shutil
import subprocess

import config

# Roots NOVA may touch (inclusive). Anything outside is refused.
USER_HOME = os.path.expanduser("~")
ALLOWED_ROOTS = [
    os.path.join(USER_HOME, "Desktop"),
    os.path.join(USER_HOME, "Documents"),
    os.path.join(USER_HOME, "Downloads"),
    config.LOGS_DIR,
    config.NOTES_DIR,
]


def _resolve(name: str, root_hint: str = "") -> str:
    """Resolve a friendly folder name to a path inside an allowed root."""
    name = (name or "").strip().strip('"').lower()
    known = {
        "desktop": os.path.join(USER_HOME, "Desktop"),
        "documents": os.path.join(USER_HOME, "Documents"),
        "downloads": os.path.join(USER_HOME, "Downloads"),
        "notes": config.NOTES_DIR,
    }
    if name in known:
        return known[name]
    # allow "downloads/myfile" style sub-paths
    base = name.split("/")[0].split("\\")[0]
    if base in known:
        return os.path.join(known[base], *name.split("/")[1:])
    if root_hint and os.path.isdir(root_hint):
        return os.path.join(root_hint, name)
    return ""


def _in_allowed_roots(path: str) -> bool:
    real = os.path.realpath(path)
    for root in ALLOWED_ROOTS:
        try:
            if os.path.commonpath([real, os.path.realpath(root)]) == os.path.realpath(root):
                return True
        except Exception:
            continue
    return False


def create_folder(name: str, where: str = "Desktop"):
    if not name:
        return "What should the folder be called, sir?"
    base = _resolve(where)
    if not base or not os.path.isdir(base):
        # 'where' must be a *known* location, never an arbitrary path
        return "I only manage folders in your Desktop, Documents or Downloads, sir."
    path = os.path.join(base, name.strip().strip('"'))
    if not _in_allowed_roots(path):
        return "I only manage folders in your Desktop, Documents or Downloads, sir."
    try:
        os.makedirs(path, exist_ok=False)
        return f"Folder '{name}' created, sir."
    except FileExistsError:
        return f"'{name}' already exists there, sir."
    except Exception as e:
        return f"The folder didn't materialize, sir: {e}"


def create_text_file(name: str, body: str = "", where: str = "Desktop"):
    if not name:
        return "And the file should be called…?"
    base = _resolve(where)
    if not base or not os.path.isdir(base):
        return "I only write files in your Desktop, Documents or Downloads, sir."
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip() or "file"
    path = os.path.join(base, safe + ".txt")
    if not _in_allowed_roots(path):
        return "I only write files in your Desktop, Documents or Downloads, sir."
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        return f"Created {safe}.txt, sir."
    except Exception as e:
        return f"The file didn't save, sir: {e}"


def open_folder(name: str):
    path = _resolve(name)
    if not path or not os.path.isdir(path):
        return f"I can't find a folder called {name}, sir."
    try:
        subprocess.Popen(["explorer", path], creationflags=subprocess.CREATE_NO_WINDOW)
        return f"Opening your {os.path.basename(path)} folder, sir."
    except Exception:
        return f"{name} refused to open, sir."


def list_folder(name: str, limit: int = 12):
    path = _resolve(name)
    if not path or not os.path.isdir(path):
        return f"I can't find a folder called {name}, sir."
    try:
        entries = sorted(os.listdir(path))[:limit]
        if not entries:
            return f"{name} is empty, sir."
        more = len(os.listdir(path)) - len(entries)
        tail = f" — and {more} more" if more > 0 else ""
        return f"{name.capitalize()} holds: {', '.join(entries)}{tail}, sir."
    except Exception as e:
        return f"I couldn't read that folder, sir: {e}"


def find_files(pattern: str, where: str = "Documents", limit: int = 8):
    if not pattern:
        return "What am I looking for, sir?"
    path = _resolve(where)
    if not path or not os.path.isdir(path):
        return f"I can't search {where} — I can't find it."
    needle = pattern.lower().strip()
    hits = []
    for root, _dirs, files in os.walk(path):
        for f in files:
            if needle in f.lower():
                hits.append(os.path.join(root, f))
                if len(hits) >= limit:
                    break
        if len(hits) >= limit:
            break
    if not hits:
        return f"No files matching '{pattern}' in {where}, sir."
    return f"Found {len(hits)} matching file(s), sir: " + ", ".join(
        os.path.basename(h) for h in hits
    ) + "."


def rename_file(old: str, new: str, where: str = "Desktop"):
    base = _resolve(where)
    if not base or not os.path.isdir(base):
        return "I only rename files inside your Desktop, Documents or Downloads, sir."
    src = os.path.join(base, old.strip().strip('"'))
    dst = os.path.join(base, new.strip().strip('"'))
    if not (_in_allowed_roots(src) and _in_allowed_roots(dst)):
        return "I only rename files inside your Desktop, Documents or Downloads, sir."
    if not os.path.exists(src):
        return f"I can't find {old} there, sir."
    try:
        os.rename(src, dst)
        return f"Renamed to {new}, sir."
    except Exception as e:
        return f"The rename failed, sir: {e}"


def move_file(name: str, dest_folder: str):
    src = _resolve(name)
    dst = _resolve(dest_folder)
    if not src or not os.path.isfile(src):
        return f"I can't find {name}, sir."
    if not dst or not os.path.isdir(dst):
        return f"I can't find the {dest_folder} folder, sir."
    if not (_in_allowed_roots(src) and _in_allowed_roots(dst)):
        return "I only move files between Desktop, Documents and Downloads, sir."
    try:
        shutil.move(src, os.path.join(dst, os.path.basename(src)))
        return f"Moved {os.path.basename(src)} to {dest_folder}, sir."
    except Exception as e:
        return f"The move failed, sir: {e}"


def request_delete(name: str, where: str = "Desktop"):
    """
    Returns a pending-confirmation descriptor — never deletes directly.
    main.py stores it and only calls execute_delete() after 'confirm'.
    """
    base = _resolve(where)
    if not base or not os.path.isdir(base):
        return None, "I only delete files inside your Desktop, Documents or Downloads, sir."
    path = os.path.join(base, name.strip().strip('"'))
    if not _in_allowed_roots(path):
        return None, "I only delete files inside your Desktop, Documents or Downloads, sir."
    if not os.path.exists(path):
        return None, f"I can't find {name} there, sir."
    return {"path": path, "name": name}, ""


def execute_delete(path: str):
    """Runs the actual delete — called ONLY after confirmation."""
    if not _in_allowed_roots(path):
        return "That file slipped out of my allowed area, sir — aborting."
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return f"Deleted, sir. {os.path.basename(path)} is no more."
    except Exception as e:
        return f"The delete failed, sir: {e}"


# ------------------------------------------------------------------ memory ----
def show_tasks():
    tasks = config.TASKS_FILE
    try:
        import json

        with open(tasks, "r", encoding="utf-8") as f:
            data = json.load(f)
        pending = data.get("pending", [])
        if not pending:
            return "Nothing pending on your list, sir."
        return f"You have {len(pending)} pending item(s), sir: " + "; ".join(pending[:6]) + "."
    except Exception:
        return "Your task list is empty, sir."


def show_reminders(state_obj):
    rem = getattr(state_obj, "pending_tasks", [])
    if not rem:
        return "No reminders standing, sir."
    return "Currently scheduled: " + "; ".join(str(r) for r in rem[:6]) + ", sir."
