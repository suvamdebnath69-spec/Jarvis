"""
test_local_first.py — NOVA's local-first pipeline test suite.

Tests the FULL pipeline: input -> classifier -> router -> handler -> result.
Dangerous actions (shutdown/restart/sleep/delete) are tested with mocks so
nothing destructive ever runs. Real hardware actions (volume, brightness,
media keys) run for real — that's the point (spec §30: the volume actually
changing is success).

Run from project root:  python tests/test_local_first.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
from contextlib import redirect_stdout
from unittest.mock import patch

import config

RESULTS = {"pass": 0, "fail": 0}
FAILURES = []


def check(name, fn):
    """fn() returns (ok, detail). Records result; never raises."""
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"EXCEPTION: {e}"
    if ok:
        RESULTS["pass"] += 1
        print(f"  PASS  {name}")
    else:
        RESULTS["fail"] += 1
        FAILURES.append((name, detail))
        print(f"  FAIL  {name}  ->  {detail}")


def route(text):
    """Run a command through handle_command with TTS muted."""
    import main

    with patch.object(main.tts, "say", lambda *_: None):
        return main.handle_command(text)


def route_silent(text):
    """route() without printing brain output (redirects stdout during LLM calls)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        return route(text)


def classify_only(text):
    """Understanding only — no handler runs (used for routing tables)."""
    from core.fast_path import fast_path

    return fast_path.understand(text)


# ===================================================================== tests ====
def test_routing():
    print("\n== ROUTING: local intents must be recognized and executed locally ==")
    local_cases = [
        ("what time is it", "GET_TIME"),
        ("what is the date", "GET_DATE"),
        ("what day is today", "GET_DAY"),
        ("take a screenshot", "SCREENSHOT"),
        ("lock my pc", "LOCK_SCREEN"),
        ("mute", "MUTE"),
        ("unmute", "UNMUTE"),
        ("turn up the volume", "VOLUME_UP"),
        ("turn down the volume", "VOLUME_DOWN"),
        ("set volume to 40", "SET_VOLUME"),
        ("play music", "PLAY_MUSIC"),
        ("pause the music", "PAUSE_MUSIC"),
        ("next track", "NEXT_TRACK"),
        ("previous track", "PREV_TRACK"),
        ("calculate 45 times 12", "CALCULATE"),
        ("what is 15 percent of 800", "CALCULATE"),
        ("open notepad", "OPEN_APP"),
        ("close notepad", "CLOSE_APP"),
        ("open youtube", "OPEN_WEBSITE"),
        ("open youtube in incognito", "OPEN_WEBSITE"),
        ("remind me to study in 10 minutes", "REMINDER"),
        ("show my tasks", "LIST_TASKS"),
        ("what reminders do I have", "LIST_REMINDERS"),
        ("create a folder called NovaTestFolder", "CREATE_FOLDER"),
        ("open my downloads folder", "OPEN_FOLDER"),
        ("show files in downloads", "LIST_FOLDER"),
    ]
    for text, want in local_cases:
        def make(text=text, want=want):
            # classify ONLY — routing tests must not fire real handlers
            # (e.g. 'lock my pc' really locking the workstation mid-suite)
            u = classify_only(text)
            ok = u["intent"] == want and (u["source"] == "rule" or u["confidence"] >= config.CONFIDENCE_FLOOR)
            return (ok, f"got intent={u['intent']} source={u['source']} conf={u['confidence']:.2f}")
        check(f"'{text}' -> {want} (local)", make)


def test_execution_real():
    print("\n== EXECUTION: real local actions (safe hardware ops) ==")

    def calc():
        r = route_silent("calculate 45 times 12")
        return ("540" in r["reply"], r["reply"])

    check("calculate 45 times 12 -> 540", calc)

    def pct():
        r = route_silent("what is 15 percent of 800")
        return ("120" in r["reply"], r["reply"])

    check("15 percent of 800 -> 120", pct)

    def power_math():
        r = route_silent("what is 2 to the power of 8")
        return ("256" in r["reply"], r["reply"])

    check("2 to the power of 8 -> 256", power_math)

    def injection():
        r = route_silent("calculate __import__('os').system('echo pwned')")
        return ("pwned" not in r["reply"] and "parse" in r["reply"].lower(), r["reply"])

    check("calculator rejects code injection", injection)

    def volume_change():
        from actions import system

        before = system.get_volume()
        r = route_silent("set volume to 73")
        after = system.get_volume()
        return ("73" in after and "73" in r["reply"], f"{before} -> {after}")

    check("set volume to 73 actually sets 73", volume_change)

    def screenshot():
        r = route_silent("take a screenshot")
        return ("saved" in r["reply"].lower(), r["reply"])

    check("screenshot saves a file", screenshot)

    def date_local():
        import datetime

        r = route_silent("what is the date")
        today = datetime.date.today().strftime("%B %d")
        return (today in r["reply"], f"'{today}' in '{r['reply']}'")

    check("date answered from datetime (not LLM)", date_local)


def test_confirmations():
    print("\n== CONFIRMATIONS: dangerous actions require explicit confirm ==")

    def shutdown_pending():
        r = route_silent("shut down my pc")
        pending = __import__("actions.registry", fromlist=["registry"]).peek_pending()
        ok = ("confirm" in r["reply"].lower() and pending is not None
              and pending.get("kind") == "shutdown")
        __import__("actions.registry", fromlist=["registry"]).cancel_pending()
        return (ok, f"reply='{r['reply'][:60]}' pending={pending}")

    check("'shut down my pc' asks for confirmation, does NOT execute", shutdown_pending)

    def confirm_flow():
        import actions.registry as registry
        from actions import system

        executed = []
        with patch.object(system, "execute_power", lambda kind: executed.append(kind) or "executed"):
            r1 = route_silent("restart the pc")
            pending = registry.peek_pending()
            r2 = route_silent("confirm")
        # prompt must offer both paths; 'confirm' must have executed exactly once
        return (pending is not None and executed == ["restart"]
                and "confirm" in r1["reply"].lower() and "cancel" in r1["reply"].lower(),
                f"pending={pending} executed={executed} r1={r1['reply'][:60]}")

    check("'restart the pc' + 'confirm' executes exactly once (mocked)", confirm_flow)

    def cancel_flow():
        import actions.registry as registry
        from actions import system

        executed = []
        with patch.object(system, "execute_power", lambda kind: executed.append(kind) or "executed"):
            route_silent("put my pc to sleep")
            r2 = route_silent("cancel")
        return (executed == [] and "cancel" in r2["reply"].lower(), f"executed={executed} r2={r2['reply'][:50]}")

    check("'sleep' + 'cancel' never executes", cancel_flow)

    def stale_confirm():
        import actions.registry as registry

        # no pending action: 'confirm' must NOT execute anything
        registry.cancel_pending()
        r = route_silent("confirm")
        return ("nothing pending" in r["reply"].lower(), r["reply"])

    check("bare 'confirm' with nothing pending is refused", stale_confirm)

    def conversation_yes():
        # a friendly 'yes' in conversation must not trip the confirm path
        r = route_silent("yes I would love that")
        return (r.get("intent") != "CONFIRM", f"intent={r.get('intent')}")

    check("conversational 'yes' is not treated as confirmation", conversation_yes)

    def delete_confirm():
        import actions.registry as registry
        from actions import files
        import os

        # make a real scratch file in an allowed root
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        scratch = os.path.join(desktop, "nova_test_delete_me.txt")
        with open(scratch, "w") as f:
            f.write("x")
        executed = []
        with patch.object(files, "execute_delete", lambda path: executed.append(path) or "deleted"):
            r1 = route_silent("delete nova_test_delete_me.txt from the desktop")
            pending = registry.peek_pending()
            r2 = route_silent("confirm")
        if os.path.exists(scratch):
            os.remove(scratch)
        return (executed == [scratch] and "confirm" in r1["reply"].lower(),
                f"executed={executed} r1={r1['reply'][:50]} r2={r2['reply'][:50]}")

    check("file delete requires confirm, then executes (mocked)", delete_confirm)


def test_safety():
    print("\n== SAFETY: classifier must not confuse lookalikes ==")

    def shutdown_app():
        u = route_silent("shut down chrome")
        return (u.get("intent") == "CLOSE_APP", f"intent={u.get('intent')}")

    check("'shut down chrome' stays CLOSE_APP (not SHUTDOWN)", shutdown_app)

    def time_not_llm():
        r = route_silent("what time is it")
        return (r.get("route") == "local", f"route={r.get('route')}")

    check("'what time is it' never reaches the LLM", time_not_llm)

    def question_to_llm():
        r = route_silent("why is the sky blue")
        return (r.get("intent") == "CHAT", f"intent={r.get('intent')}")

    check("'why...' goes to conversation (LLM)", question_to_llm)

    def search_vs_knowledge():
        u_search = route_silent("search the web for python tutorials")
        u_know = route_silent("what is photosynthesis")
        return (u_search.get("intent") == "SEARCH_WEB" and u_know.get("intent") == "CHAT",
                f"search={u_search.get('intent')} knowledge={u_know.get('intent')}")

    check("explicit search -> web; knowledge question -> LLM", search_vs_knowledge)


def test_files():
    print("\n== FILES: local file ops in allowed roots ==")

    def folder_roundtrip():
        r1 = route_silent("create a folder called NovaTestDir")
        import os

        path = os.path.join(os.path.expanduser("~"), "Desktop", "NovaTestDir")
        exists = os.path.isdir(path)
        if exists:
            os.rmdir(path)
        return (exists and "created" in r1["reply"].lower(), f"reply={r1['reply']} exists={exists}")

    check("create folder works on Desktop", folder_roundtrip)

    def outside_refused():
        from actions import files

        result = files.create_folder("evil", where="C:\\Windows")
        return ("only manage" in result or "only write" in result, result)

    check("folder creation outside allowed roots is refused", outside_refused)


def main_brain_think():
    import main

    return type("B", (), {"think_stream": staticmethod(lambda t, cb=None: "")})()


def main():
    print("=" * 64)
    print("NOVA LOCAL-FIRST PIPELINE TEST SUITE")
    print("=" * 64)

    test_routing()
    test_execution_real()
    test_confirmations()
    test_safety()
    test_files()

    print("\n" + "=" * 64)
    total = RESULTS["pass"] + RESULTS["fail"]
    print(f"RESULTS: {RESULTS['pass']}/{total} passed, {RESULTS['fail']} failed")
    if FAILURES:
        print("\nFailures:")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
    print("=" * 64)
    return RESULTS["fail"]


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
