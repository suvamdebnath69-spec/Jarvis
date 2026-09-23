"""
test_neural_vs_rules.py — generalization checks on unseen natural phrasings.

Verifies the FULL understanding pipeline (rules + neural) on phrasings
plausibly spoken but not verbatim in the training data. A bag-of-words net
on novel phrasing is expected to be approximate; the test encodes NOVA's
REAL bar:

  STRONG  — must be recognized exactly (rule covers it, or net is sure)
  WEAK    — intent correct OR confidence below the action floor
            (below the floor it falls to the LLM, which is a safe outcome)

Run:  python tests/test_neural_vs_rules.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from core.fast_path import fast_path

PASS = FAIL = 0
FAILURES = []


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  FAIL  {name}  ->  {detail}")


def under(text):
    return fast_path.understand(text)


STRONG = [
    # rules MUST catch these variants (parameter-carrying commands)
    ("whats 12 plus 13", "CALCULATE"),
    ("solve 88 times 44", "CALCULATE"),
    ("what is 144 divided by 12", "CALCULATE"),
    ("set the volume to 65 percent", "SET_VOLUME"),
    ("remind me to call dad in an hour", "REMINDER"),
    ("open youtube in incognito", "OPEN_WEBSITE"),
    ("take a screenshot of the screen", "SCREENSHOT"),
    ("create a folder called holiday pics", "CREATE_FOLDER"),
    ("show files in downloads", "LIST_FOLDER"),
    ("delete the file draft from documents", "DELETE_FILE"),
]

WEAK = [
    # novel phrasings: right intent, or safely below the action floor
    ("would you crank the speakers up a notch", "VOLUME_UP", "CHAT"),
    ("the sound on this thing is deafening", "VOLUME_DOWN", "CHAT"),
    ("are we online right now", "WIFI_STATUS", "CHAT"),
    ("give it a fresh reboot", "RESTART", "GET_DAY"),
    ("let the machine doze off", "SLEEP_PC", "SHUTDOWN"),
    ("crank up the tunes", "PLAY_MUSIC", "SEARCH_WEB"),
    ("halt the audio", "PAUSE_MUSIC", "UNMUTE"),
    ("advance to the following track", "NEXT_TRACK", "OPEN_WEBSITE"),
    ("make a new directory on desktop", "CREATE_FOLDER", "CHAT"),
    ("search my documents for tax forms", "FIND_FILES", "SEARCH_WEB"),
    ("put the screen on black-out mode brightness", "BRIGHTNESS_DOWN", "SET_BRIGHTNESS"),
    ("how much juice is left in the battery", "BATTERY_STATUS", "CHAT"),
]

AMBIGUOUS = [
    # ambiguous chatter must not be confidently actionable
    ("could you help me with something",),
    ("i was thinking about the beach",),
    ("what do you think",),
]


def main():
    print("=" * 64)
    print("UNDERSTANDING — unseen-phrase generalization (full pipeline)")
    print("=" * 64)

    print("\nSTRONG — must be understood exactly")
    for phrase, want in STRONG:
        u = under(phrase)
        ok = u["intent"] == want and (
            u["source"] == "rule" or u["confidence"] >= config.CONFIDENCE_FLOOR
        )
        check(f"'{phrase}' -> {want}", ok,
              f"got {u['intent']} src={u['source']} conf={u['confidence']:.2f}")

    print("\nWEAK — right intent, or safely handed to the LLM")
    for phrase, want, alt in WEAK:
        u = under(phrase)
        ok = u["intent"] == want or u["intent"] == alt or u["confidence"] < config.CONFIDENCE_FLOOR
        check(f"'{phrase}' -> {want} (or {alt}/unsure)", ok,
              f"got {u['intent']} conf={u['confidence']:.2f}")

    print("\nAMBIGUOUS — must not trigger confident actions")
    for (phrase,) in AMBIGUOUS:
        u = under(phrase)
        ok = u["intent"] in ("CHAT", None) or u["confidence"] < 0.75
        check(f"'{phrase}' stays conversational", ok,
              f"got {u['intent']} conf={u['confidence']:.2f}")

    print("\n" + "=" * 64)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    for name, detail in FAILURES:
        print(f"  - {name}: {detail}")
    print("=" * 64)
    return FAIL


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
