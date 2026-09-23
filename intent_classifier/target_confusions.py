"""Third pass: targeted examples for actual evaluation confusions (spec §22)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PHRASES = os.path.join(HERE, "data", "phrases.txt")

TOPUP = {
    "VOLUME_DOWN": [
        "turn down the sound",
        "make the volume lower",
        "decrease the sound level",
        "the volume needs to go down",
        "quiet it down",
        "drop the volume",
        "volume lower please",
        "bring the sound down",
    ],
    "VOLUME_UP": [
        "turn up the sound",
        "raise the audio level",
        "the volume needs to go up",
        "louder volume please",
        "lift the volume",
        "sound higher please",
    ],
    "UNMUTE": [
        "unmute the system",
        "turn the mute off",
        "sound on again",
        "take the mute off please",
        "turn my sound back on",
        "unmute the machine",
    ],
    "MUTE": [
        "mute the system",
        "silence it",
        "sound off please",
        "mute everything",
        "put it on mute",
    ],
    "SCROLL": [
        "scroll down the page",
        "scroll up a bit",
        "scroll the window",
        "page down please",
        "page up",
        "scroll further down",
    ],
    "OPEN_WEBSITE": [
        "go to youtube",
        "open the website reddit",
        "visit wikipedia",
        "take me to google",
        "open stackoverflow",
        "navigate to github",
        "visit the website netflix",
    ],
    "OPEN_APP": [
        "open the chrome app",
        "launch the notepad application",
        "open spotify program",
        "start the discord app",
        "run the calculator application",
        "open my vscode editor",
    ],
    "CLOSE_APP": [
        "close the chrome app",
        "quit the notepad application",
        "exit the spotify program",
        "kill the discord app process",
    ],
    "SCREENSHOT": [
        "take a screenshot of my display",
        "capture the screen now",
        "snap a screenshot",
        "screenshot my desktop",
        "grab the screen image",
    ],
    "BATTERY_STATUS": [
        "battery level check",
        "what is my battery at",
        "how is the battery doing",
        "remaining battery power",
        "battery charge status",
        "power level remaining",
    ],
    "BRIGHTNESS_DOWN": [
        "lower the screen brightness",
        "reduce the display brightness",
        "dim my screen",
        "turn the display brightness down",
        "brightness lower",
    ],
    "BRIGHTNESS_UP": [
        "raise the screen brightness",
        "increase display brightness",
        "brighten my display",
        "turn the screen brightness up",
        "brightness higher",
    ],
    "SET_BRIGHTNESS": [
        "set the brightness level to 75",
        "adjust brightness to 55 percent",
        "set my screen brightness at 35",
        "brightness level 20",
        "set display brightness to 90 percent",
    ],
    "SET_VOLUME": [
        "set the volume level to 45",
        "adjust volume to 60 percent",
        "set my sound at 35",
        "volume level 80",
        "set the audio to 25 percent",
    ],
    "SLEEP_PC": [
        "sleep the computer",
        "put this machine in sleep mode",
        "make my pc sleep now",
        "enter sleep mode",
        "nap time for the pc",
    ],
    "CREATE_FILE": [
        "create a text file named notes today",
        "make a file called plan",
        "new text file named journal",
        "create file named budget txt",
        "make me a text file named shopping list",
    ],
    "CREATE_FOLDER": [
        "create a directory called projects",
        "make a directory named media",
        "new folder named downloads backup",
        "create directory called games",
        "make me a folder named papers",
    ],
    "CHAT": [
        "you are doing great",
        "what do you think about music",
        "tell me about yourself",
        "i feel like chatting",
        "how does this work",
        "what should I do today",
        "give me some motivation",
    ],
    "SHUTDOWN": [
        "shut down my computer now",
        "power off my machine",
        "turn off this pc",
        "shut everything down",
        "shutdown the system",
    ],
    "SEARCH_WEB": [
        "search online for hiking trails",
        "look up bread recipe on the web",
        "google the population of japan",
        "find information on the web about cars",
        "browse for cheap flights",
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
            print(f"WARNING: intent {intent} not in dataset")
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
    print(f"Added {added} targeted phrases")


if __name__ == "__main__":
    main()
