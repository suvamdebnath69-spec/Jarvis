"""
expand_dataset.py — one-shot dataset improvement (spec §3: quality over size).

1. Relabels the legacy SEARCH intent: explicit web verbs -> SEARCH_WEB,
   knowledge questions -> CHAT (the LLM knowledge path).
2. Relabels legacy WRITING -> CHAT (creative writing is the LLM's job).
3. Appends new intents for NOVA's new local capabilities with genuinely
   varied natural phrasings (no synthetic padding).

Idempotent: relabels only touch legacy SEARCH/WRITING sections; new
sections are added only if their INTENT: header is missing.

Run from the project root:  python intent_classifier/expand_dataset.py
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PHRASES = os.path.join(HERE, "data", "phrases.txt")

# legacy SEARCH line -> SEARCH_WEB when it starts with an explicit web verb
_WEB_VERB = re.compile(
    r"^(?:search|browse|google|look ?up|find|extract|check the internet|"
    r"open my browser and search)\b",
    re.I,
)

NEW_INTENTS = {
    "VOLUME_UP": [
        "turn the volume up",
        "turn up the volume",
        "volume up",
        "raise the volume",
        "increase the volume",
        "make it louder",
        "it's too quiet",
        "louder please",
        "crank the volume",
        "pump up the volume",
        "bring the volume up",
        "sound is too low",
        "turn it up",
        "the audio is too quiet",
        "boost the volume",
    ],
    "VOLUME_DOWN": [
        "turn the volume down",
        "turn down the volume",
        "volume down",
        "lower the volume",
        "decrease the volume",
        "make it quieter",
        "it's too loud",
        "quieter please",
        "bring the volume down",
        "reduce the volume",
        "the audio is too loud",
        "turn it down",
        "sound is too high",
        "tone it down a little",
    ],
    "SET_VOLUME": [
        "set volume to 50",
        "set the volume to 30 percent",
        "volume to 20",
        "put the volume at 75",
        "set volume at 100",
        "set the audio level to 40 percent",
        "make the volume 60 percent",
        "set volume 10",
        "volume 30 percent",
        "put volume to 65",
    ],
    "MUTE": [
        "mute",
        "mute the volume",
        "mute the audio",
        "silence the sound",
        "mute my computer",
        "mute it please",
        "turn the sound off",
        "mute the pc",
        "silence please",
    ],
    "UNMUTE": [
        "unmute",
        "unmute the volume",
        "unmute the audio",
        "turn the sound back on",
        "unmute my computer",
        "give me sound again",
    ],
    "GET_VOLUME": [
        "what's the volume",
        "what is the volume level",
        "how loud is the volume",
        "volume status",
        "what's the current volume",
        "check the volume",
        "how high is the sound set",
    ],
    "BRIGHTNESS_UP": [
        "turn the brightness up",
        "brightness up",
        "increase the brightness",
        "raise the brightness",
        "make the screen brighter",
        "it's too dim",
        "make it brighter",
        "screen is too dark",
        "turn up the screen brightness",
    ],
    "BRIGHTNESS_DOWN": [
        "turn the brightness down",
        "brightness down",
        "decrease the brightness",
        "lower the brightness",
        "dim the screen",
        "make the screen dimmer",
        "it's too bright",
        "make it dimmer",
        "screen is too bright at night",
        "reduce the screen brightness",
    ],
    "SET_BRIGHTNESS": [
        "set brightness to 50",
        "set the brightness to 80 percent",
        "brightness to 30",
        "set screen brightness to 70",
        "put brightness at 40 percent",
        "brightness 90",
    ],
    "BATTERY_STATUS": [
        "what's my battery percentage",
        "what is the battery level",
        "how much battery do I have left",
        "battery status",
        "check the battery",
        "how is the battery",
        "battery life",
        "is the battery charging",
        "how much charge is left",
        "battery percentage please",
    ],
    "WIFI_STATUS": [
        "wifi status",
        "what's my wifi connection",
        "am I connected to wifi",
        "check the wifi",
        "internet status",
        "are we connected to the network",
        "what network am I on",
        "check the internet connection",
        "wifi check please",
    ],
    "SCREENSHOT": [
        "take a screenshot",
        "take a screenshot of the screen",
        "screenshot",
        "capture the screen",
        "grab a screenshot",
        "screenshot the display",
        "take a snapshot of my screen",
        "capture my screen please",
    ],
    "LOCK_SCREEN": [
        "lock my pc",
        "lock the computer",
        "lock my screen",
        "lock the workstation",
        "lock windows",
        "lock it",
        "lock my machine",
        "secure my screen",
    ],
    "SHUTDOWN": [
        "shut down my pc",
        "shut down the computer",
        "turn off the computer",
        "power off the pc",
        "shut the machine down",
        "shutdown",
        "shut down my system",
        "turn off my computer please",
        "power down the machine",
    ],
    "RESTART": [
        "restart my pc",
        "restart the computer",
        "reboot the system",
        "reboot my pc",
        "restart the machine",
        "restart",
        "reboot please",
        "restart my computer now",
    ],
    "SLEEP_PC": [
        "put my pc to sleep",
        "put the computer to sleep",
        "sleep the pc",
        "put my computer in sleep mode",
        "go to sleep mode",
        "make the computer sleep",
        "sleep my machine",
    ],
    "PLAY_MUSIC": [
        "play music",
        "play some music",
        "play a song",
        "resume the music",
        "play the track",
        "play",
        "put on some music",
        "start playing music",
        "resume playback",
    ],
    "PAUSE_MUSIC": [
        "pause",
        "pause the music",
        "pause the song",
        "hold on a second",
        "pause playback",
        "pause it",
        "stop the music playing",
        "freeze the track",
    ],
    "NEXT_TRACK": [
        "next track",
        "next song",
        "skip this track",
        "skip to the next one",
        "play the next song",
        "skip",
        "next",
        "jump to the next track",
    ],
    "PREV_TRACK": [
        "previous track",
        "previous song",
        "go back a track",
        "play the last song again",
        "previous",
        "go back to the previous song",
        "rewind to the last track",
    ],
    "GET_DATE": [
        "what's the date",
        "what is today's date",
        "what's the date today",
        "tell me the date",
        "date please",
        "what day of the month is it",
        "what's today's date",
        "the date check",
        "what is the date",
    ],
    "GET_DAY": [
        "what day is it",
        "what day is today",
        "what day are we on",
        "tell me the day",
        "what's the day today",
        "is it monday today",
        "which day of the week is it",
    ],
    "CALCULATE": [
        "calculate 45 times 12",
        "what's 25 plus 17",
        "what is 90 minus 31",
        "calculate 200 divided by 4",
        "what's 15 percent of 800",
        "what is 2 to the power of 8",
        "calculate 144 square root",
        "what's 5 squared",
        "what is 2 cubed",
        "compute 12 times 12",
        "calculate 99 times 3",
        "what's 6 divided by 2",
        "what is 8 plus 7",
        "calculate 3.5 plus 1.2",
        "what's 20 percent of 150",
    ],
    "CREATE_FOLDER": [
        "create a folder called Projects",
        "make a new folder named Work",
        "create a folder on the desktop called Notes",
        "make a folder called Test",
        "create a new folder named Archive",
        "make me a folder called Budget",
    ],
    "CREATE_FILE": [
        "create a text file called shopping",
        "make a new file called todo",
        "create a file named ideas",
        "make a text file called journal",
        "create a new text file named passwords",
    ],
    "OPEN_FOLDER": [
        "open my downloads folder",
        "open the documents folder",
        "show my desktop folder",
        "open downloads",
        "open my documents",
        "launch the desktop folder",
        "show my notes folder",
    ],
    "LIST_FOLDER": [
        "show files in downloads",
        "what's in my documents",
        "list the files on my desktop",
        "what's in downloads",
        "show what's in my notes folder",
        "list my documents",
    ],
    "FIND_FILES": [
        "find my python files in documents",
        "find report files in documents",
        "search my downloads for invoices",
        "find my resume in documents",
        "find python files",
        "search documents for project files",
    ],
    "RENAME_FILE": [
        "rename draft.txt to final.txt",
        "rename old notes to archive",
        "rename project draft to project final in documents",
        "rename my file essay to essay v2",
    ],
    "MOVE_FILE": [
        "move report.docx to documents",
        "move screenshot to downloads",
        "move my file notes to documents",
        "move invoice to documents folder",
    ],
    "DELETE_FILE": [
        "delete the file junk.txt",
        "remove old notes",
        "delete folder temp stuff on the desktop",
        "delete test file",
        "remove the file draft in documents",
    ],
    "LIST_TASKS": [
        "what tasks do I have",
        "show my tasks",
        "list my to-dos",
        "what's pending on my list",
        "which tasks are pending",
        "show my pending tasks",
    ],
    "LIST_REMINDERS": [
        "what reminders do I have",
        "list my reminders",
        "show reminders",
        "which reminders are set",
        "any reminders pending",
    ],
}

# legacy WRITING section: creative writing belongs to the LLM (CHAT)
_WRITING_TO_CHAT = True


def parse_sections():
    sections = []  # [(intent_name, [lines])]
    current = None
    with open(PHRASES, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if s.startswith("INTENT:"):
                current = (s.split("INTENT:")[1].strip(), [])
                sections.append(current)
            elif current is not None:
                current[1].append(line)
    return sections


def write_sections(sections):
    with open(PHRASES, "w", encoding="utf-8", newline="\n") as f:
        for name, lines in sections:
            f.write(f"INTENT: {name}\n\n")
            for l in lines:
                if l.strip():
                    f.write(l.rstrip() + "\n")
            f.write("\n")


def main():
    sections = parse_sections()
    existing = {name for name, _ in sections}

    # 1+2. relabel legacy SEARCH and WRITING
    for name, lines in sections:
        if name == "SEARCH":
            new_lines = []
            for l in lines:
                s = l.strip()
                if not s:
                    new_lines.append(l)
                    continue
                phrase = s[1:].strip() if s.startswith("-") else s
                target = "SEARCH_WEB" if _WEB_VERB.match(phrase) else "CHAT"
                new_lines.append(f"- {phrase}  # -> {target}")
            # rewrite in place via marker comment parsing below
            lines[:] = new_lines
        if name == "WRITING" and _WRITING_TO_CHAT:
            lines[:] = [l + "  # -> CHAT" if l.strip() else l for l in lines]

    # apply marker relabels: split sections whose lines carry "# -> X"
    out = []
    for name, lines in sections:
        if name in ("SEARCH", "WRITING"):
            buckets = {}
            for l in lines:
                m = re.search(r"#\s*->\s*(\w+)", l)
                if m:
                    buckets.setdefault(m.group(1), []).append(l.split("#")[0].rstrip())
                elif l.strip():
                    buckets.setdefault(name, []).append(l)
            for target, blines in buckets.items():
                if target in buckets and target not in (name,):
                    out.append((target, blines))
                else:
                    out.append((name, blines))
        else:
            out.append((name, lines))

    # 3. append new intents
    for intent, phrases in NEW_INTENTS.items():
        if intent not in {n for n, _ in out}:
            out.append((intent, [f"- {p}" for p in phrases]))

    # collapse duplicate section names (merge phrase lists)
    merged = []
    seen = {}
    for name, lines in out:
        if name in seen:
            merged[seen[name]] = (name, merged[seen[name]][1] + lines)
        else:
            seen[name] = len(merged)
            merged.append((name, lines))

    write_sections(merged)

    # summary
    from collections import Counter

    counts = Counter()
    cur = None
    for line in open(PHRASES, encoding="utf-8"):
        s = line.strip()
        if s.startswith("INTENT:"):
            cur = s.split(":")[1].strip()
        elif s and cur:
            counts[cur] += 1
    print("Dataset now:")
    for k, v in sorted(counts.items()):
        print(f"  {k:16} {v}")
    print(f"  {'TOTAL':16} {sum(counts.values())}")


if __name__ == "__main__":
    main()
