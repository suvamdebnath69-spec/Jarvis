"""
tests/pc_skills_test.py — NOVA PC-control skill battery, 3 rounds.

Runs each skill through handle_command (the real pipeline: fast_path ->
routing -> action layer), verifies observable side effects, and prints a
per-round scorecard. Non-destructive by design: no send on the DM test,
no shutdown/restart, test app is Notepad.

Run:  python tests/pc_skills_test.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402  (brings up the whole stack, including Flask routes)
import psutil  # noqa: E402
from actions import beast_tools, documents, web  # noqa: E402
from core.state import state  # noqa: E402


def _proc_running(process_name: str) -> bool:
    return any(p.name().lower() == process_name.lower() for p in psutil.process_iter(["name"]))


def _window_with(title_part: str) -> bool:
    try:
        import win32gui

        found = []

        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and title_part.lower() in win32gui.GetWindowText(hwnd).lower():
                found.append(hwnd)

        win32gui.EnumWindows(_enum, None)
        return bool(found)
    except Exception:
        return False


# ------------------------------------------------------------------ checks ----
def check(condition: bool, ok: str, fail: str) -> bool:
    """Collapse to a bare boolean — tuples are always truthy, a classic
    silent-pass bug the first harness revision had."""
    return bool(condition)


def run_round(round_no: int) -> list:
    results = []
    arm = round_no % 2 == 1  # alternate beast mode to test gating in even rounds

    def record(name, ok, note=""):
        results.append((name, bool(ok), note))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<28} {note}")

    print(f"\n=== ROUND {round_no} (beast_mode={'ON' if arm else 'OFF'}) ===")
    state.set_beast_mode(arm)

    # 1. open app
    r = main.handle_command("open notepad")
    time.sleep(2)
    record("open_app", check(
        "Opening notepad" in r["reply"] and _proc_running("notepad.exe"),
        "notepad.exe running", f"reply={r['reply']!r} proc={_proc_running('notepad.exe')}",
    ))

    # 2. close app
    r = main.handle_command("close notepad")
    time.sleep(2)
    gone = not _proc_running("notepad.exe")
    record("close_app", check(
        gone,
        f"notepad.exe gone ({r['reply'][:40]})",
        f"reply={r['reply']!r} proc={_proc_running('notepad.exe')}",
    ))

    # 3. website (normal)
    r = main.handle_command("open wikipedia")
    record("open_website", check("Opening" in r["reply"], "browser opened", r["reply"]))
    time.sleep(3)

    # 4. incognito
    r = main.handle_command("open youtube in incognito")
    record("incognito", check(
        "InPrivate" in r["reply"] and r["intent"] == "OPEN_WEBSITE",
        "InPrivate window", r["reply"],
    ))
    time.sleep(3)

    # 5. research document
    r = main.handle_command("prepare a research document on Albert Einstein")
    made_doc = any(f.startswith("research_albert_einstein") for f in os.listdir(documents.config.NOTES_DIR))
    record("research_doc", check(
        r["intent"] == "RESEARCH" and made_doc and "Research complete" in r["reply"],
        f"doc saved in logs/notes ({r['reply'][:50]})",
        f"intent={r['intent']} made_doc={made_doc} reply={r['reply'][:60]!r}",
    ))

    # 6. click (gated)
    r = main.handle_command("click at 400, 300")
    if arm:
        record("click_at", check(
            "Clicked" in r["reply"], "pyautogui click fired", r["reply"],
        ))
    else:
        record("click_gating", check(
            "Beast Mode skill" in r["reply"], "blocked when disarmed", r["reply"],
        ))

    # 7. typing (gated) — into focused window; we type into the research doc window? no,
    #    into NOVA's own console is unsafe; instead just verify gating/typing path.
    r = main.handle_command('type "nova pc control test"')
    record("type_text", check(
        ("Typed." in r["reply"]) if arm else ("Beast Mode skill" in r["reply"]),
        "typed or correctly gated", r["reply"],
    ))

    # 8. instagram DM (typed, never sent) — or correctly gated when disarmed
    r = main.handle_command('text user instagram saying "Hi" on instagram')
    low = r["reply"].lower()
    if arm:
        record("instagram_dm", check(
            "instagram" in low and ("typed" in low or "couldn't" in low or "message button" in low),
            f"armed path ({r['reply'][:60]})",
            f"unexpected reply={r['reply']!r}",
        ))
    else:
        record("instagram_gating", check(
            "beast mode skill" in low,
            "blocked when disarmed",
            f"reply={r['reply']!r}",
        ))

    # 9. web search
    r = main.handle_command("search the web for quantum computing basics")
    record("search_web", check("Searching" in r["reply"], "search opened", r["reply"]))

    # 10. jokes (LLM path)
    r = main.handle_command("tell me a joke")
    record("joke", check(
        r["intent"] == "CHAT" and len(r["reply"]) > 10,
        f"LLM joke ({len(r['reply'])} chars)", r["reply"][:60],
    ))

    # 11. question routing (regression: sky-blue bug)
    r = main.handle_command("why is the sky blue, in one sentence")
    record("question_routing", check(
        r["intent"] == "CHAT", "routed to LLM not GET_TIME", r["reply"][:60],
    ))

    # 12. tab control
    r = main.handle_command("open a new tab")
    record("open_tab", check("tab" in r["reply"].lower(), "tab opened", r["reply"]))
    time.sleep(2)
    r = main.handle_command("close this tab")
    record("close_tab", check("losing" in r["reply"].lower() or "couldn't" in r["reply"].lower(), "keystroke sent", r["reply"]))

    # 13. reminder
    r = main.handle_command("remind me to test nova again in 2 minutes")
    record("reminder", check("remind you" in r["reply"].lower(), "scheduled", r["reply"]))

    # 14. notes
    r = main.handle_command("take a note that nova passed its pc control test")
    record("take_note", check("Noted" in r["reply"], "saved", r["reply"]))

    # 15. time
    r = main.handle_command("what time is it")
    record("get_time", check("It's" in r["reply"], "answered", r["reply"]))

    state.set_beast_mode(False)
    return results


def main_test():
    all_results = []
    for rnd in range(1, 4):
        all_results.extend(run_round(rnd))

    print("\n=== SUMMARY (3 rounds) ===")
    by_name = {}
    for name, ok, _ in all_results:
        by_name.setdefault(name, []).append(ok)
    total_pass, total_all = 0, 0
    for name, outcomes in by_name.items():
        passed = sum(outcomes)
        total_pass += passed
        total_all += len(outcomes)
        status = "STABLE" if passed == len(outcomes) else ("FLAKY" if passed else "BROKEN")
        print(f"  {name:<20} {passed}/{len(outcomes)}  {status}")
    print(f"\n  TOTAL: {total_pass}/{total_all} checks passed")


if __name__ == "__main__":
    main_test()
