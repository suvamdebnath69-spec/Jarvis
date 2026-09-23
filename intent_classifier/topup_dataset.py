"""Second pass: top up the smallest new intents with more varied phrasings."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PHRASES = os.path.join(HERE, "data", "phrases.txt")

TOPUP = {
    "CREATE_FILE": [
        "create a text file called groceries on the desktop",
        "make a file named meeting notes",
        "create a new file called budget",
        "make a text file named reminders",
        "create a file called password list",
    ],
    "CREATE_FOLDER": [
        "create a folder named photos backup",
        "make a folder called learning on the desktop",
        "create a new folder called invoices",
        "make a folder named workouts",
        "create a folder called receipts in documents",
    ],
    "DELETE_FILE": [
        "delete old draft from the desktop",
        "remove temp file from downloads",
        "delete the notes file",
        "delete screenshot from the desktop",
        "remove backup folder",
    ],
    "MOVE_FILE": [
        "move homework.txt to documents",
        "move my spreadsheet to documents",
        "move the pdf to downloads",
        "move presentation file to documents",
    ],
    "RENAME_FILE": [
        "rename temp to temp backup",
        "rename note.txt to ideas.txt",
        "rename my file draft to submission",
        "rename chart to final chart",
        "rename photo1 to vacation photo",
    ],
    "LIST_REMINDERS": [
        "what reminders are set",
        "do I have any reminders",
        "show my active reminders",
        "what have you reminded me about",
        "list pending reminders",
        "any reminders coming up",
    ],
    "GET_DAY": [
        "what day is it today",
        "which weekday is it",
        "tell me today's day",
        "what day of the week are we in",
        "day check",
    ],
    "GET_DATE": [
        "what is the date today",
        "tell me today's date",
        "what's the current date",
        "date check",
        "what date is it",
    ],
    "GET_VOLUME": [
        "what's the volume set at",
        "how loud is it set",
        "check volume level",
        "current volume please",
        "what level is the sound",
    ],
    "SET_BRIGHTNESS": [
        "set the brightness to 65 percent",
        "brightness to 45",
        "set screen brightness at 25",
        "put the brightness to 85",
        "set brightness 100",
    ],
    "UNMUTE": [
        "unmute the pc",
        "unmute the sound",
        "take it off mute",
        "restore the audio",
        "unmute it",
    ],
    "SET_VOLUME": [
        "set the volume at 15",
        "volume to 85 percent",
        "set volume level to 55",
        "put the sound at 25 percent",
        "set audio to 70",
    ],
    "SLEEP_PC": [
        "put my computer to sleep",
        "sleep mode now",
        "put the machine to sleep",
        "send the pc to sleep",
        "let the computer sleep",
    ],
    "RESTART": [
        "reboot the computer",
        "restart the pc please",
        "reboot my machine",
        "restart windows",
        "restart this computer",
    ],
    "SHUTDOWN": [
        "shut down the pc",
        "turn off my pc",
        "power off the computer",
        "shut down windows",
        "turn the machine off",
    ],
    "LOCK_SCREEN": [
        "lock the pc",
        "lock my computer screen",
        "lock windows now",
        "lock the machine",
        "lock my desktop",
    ],
    "SCREENSHOT": [
        "screenshot the screen",
        "take a screen capture",
        "capture the display",
        "take a screenshot now",
        "snap my screen",
    ],
    "WIFI_STATUS": [
        "what's the wifi status",
        "which wifi network am I on",
        "check my internet connection",
        "am I on the internet",
        "network status please",
    ],
    "BATTERY_STATUS": [
        "battery percentage",
        "how much battery is left",
        "what's the charge level",
        "check my battery level",
        "is my laptop charging",
    ],
    "LIST_TASKS": [
        "what's on my task list",
        "show pending tasks",
        "list my tasks",
        "what to-dos are pending",
        "check my task list",
    ],
    "LIST_FOLDER": [
        "show my downloads files",
        "what files are in documents",
        "list files on desktop",
        "what's inside my notes",
        "show the files in downloads",
    ],
    "OPEN_FOLDER": [
        "open the downloads folder",
        "show my documents folder",
        "open my desktop",
        "launch my notes folder",
        "open documents please",
    ],
    "PAUSE_MUSIC": [
        "pause the song",
        "pause the track",
        "hold the music",
        "pause it please",
        "stop playing for a moment",
    ],
    "PLAY_MUSIC": [
        "play my music",
        "start the music",
        "play a track",
        "resume my song",
        "music on",
    ],
    "NEXT_TRACK": [
        "next song please",
        "skip this song",
        "play the next track",
        "advance to the next song",
        "skip forward",
    ],
    "PREV_TRACK": [
        "last track",
        "go to the previous song",
        "play the previous track",
        "back one song",
        "skip backward",
    ],
    "BRIGHTNESS_UP": [
        "brighten the screen",
        "raise the screen brightness",
        "turn brightness up",
        "increase screen brightness",
        "screen too dim",
    ],
    "BRIGHTNESS_DOWN": [
        "darken the screen",
        "reduce brightness",
        "turn down the brightness",
        "decrease the screen brightness",
        "lower screen brightness",
    ],
    "MUTE": [
        "mute the sound",
        "mute please",
        "silence the audio",
        "cut the sound",
        "mute the system audio",
    ],
    "VOLUME_UP": [
        "louder",
        "raise volume",
        "turn up sound",
        "volume higher",
        "increase audio",
    ],
    "VOLUME_DOWN": [
        "quieter",
        "lower volume",
        "turn down sound",
        "volume lower",
        "decrease audio",
    ],
    "CALCULATE": [
        "calculate 13 times 7",
        "what's 120 divided by 8",
        "what is 45 plus 55",
        "calculate 81 minus 19",
        "what's 3 to the power of 4",
        "what is 10 percent of 250",
        "calculate 64 square root",
        "what's 9 squared",
    ],
}


def main():
    sections = []
    current = None
    with open(PHRASES, "r", encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if s.startswith("INTENT:"):
                current = (s.split("INTENT:")[1].strip(), [])
                sections.append(current)
            elif current is not None and s:
                current[1].append(s)

    index = {name: i for i, (name, _) in enumerate(sections)}
    added = 0
    for intent, phrases in TOPUP.items():
        if intent not in index:
            continue
        existing = {l[2:].strip().lower() for l in sections[index[intent]][1]}
        for p in phrases:
            if p.lower() not in existing:
                sections[index[intent]][1].append(f"- {p}")
                added += 1

    with open(PHRASES, "w", encoding="utf-8", newline="\n") as f:
        for name, lines in sections:
            f.write(f"INTENT: {name}\n\n")
            for l in lines:
                f.write(l + "\n")
            f.write("\n")
    print(f"Added {added} phrases")


if __name__ == "__main__":
    main()
