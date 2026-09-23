"""
scale_dataset.py — bring EVERY intent above 100 examples (user requirement).

Strategy: for each intent below the target, generate natural command
variants from multiple hand-authored template families with slot banks
(verbs x objects x politeness x parameters). Candidates are deduped
case-insensitively against the whole dataset and each other, then sampled
to just above the target. Existing phrases are never touched.

Idempotent: reruns only add what's missing.

Run from project root:  python intent_classifier/scale_dataset.py
"""

import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
PHRASES = os.path.join(HERE, "data", "phrases.txt")
TARGET = 105  # every intent must exceed 100

rng = random.Random(42)

POLITE = ["", "please ", "nova, ", "can you ", "could you ", "hey nova, "]

APPS = ["chrome", "spotify", "discord", "notepad", "calculator", "vscode",
        "word", "terminal", "powershell", "file explorer", "edge", "firefox"]
SITES = ["youtube", "google", "github", "instagram", "reddit", "wikipedia",
         "netflix", "amazon", "stackoverflow", "gmail", "twitter", "maps"]
NOTE_FILES = ["notes", "todo", "journal", "ideas", "plan", "shopping list",
              "report", "summary", "draft", "diary", "log", "agenda"]
FOLDERS = ["projects", "work", "archive", "backups", "temp", "media",
           "school", "finance", "photos", "receipts"]
FILE_PATS = ["resume", "invoice", "report", "python", "essay", "photo",
             "budget", "contract", "homework", "presentation", "certificate", "scan"]
LEVELS = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]
CALC_PAIRS = [(45, 12, "times"), (12, 7, "times"), (200, 4, "divided by"),
              (120, 8, "divided by"), (25, 17, "plus"), (90, 31, "minus"),
              (55, 45, "plus"), (81, 19, "minus"), (144, 12, "divided by"),
              (13, 9, "times"), (48, 6, "divided by"), (67, 33, "plus")]
CALC_WORDS = ["times", "multiplied by", "plus", "minus", "divided by"]
CALC_NUMS = [(6, 4), (12, 3), (9, 8), (15, 7), (22, 11), (40, 25), (18, 6),
             (31, 14), (27, 9), (50, 50), (100, 37), (8, 5)]
MATHS = [(15, 800), (20, 150), (10, 250), (25, 400), (5, 90), (30, 60),
         (50, 200), (12, 75), (8, 45), (40, 500), (18, 90), (35, 700)]
PCT_PER = ["15 percent of 800", "20 percent of 150", "10 percent of 250",
           "25 percent of 400", "50 percent of 200", "30 percent of 60",
           "5 percent of 90", "40 percent of 500", "12 percent of 75"]
POWERS = [(2, 8), (3, 4), (5, 3), (2, 10), (4, 3), (6, 2), (10, 3), (7, 2)]
SQRTS = [144, 169, 64, 81, 100, 25, 36, 49, 121, 9, 16, 225]
REM_TASKS = ["to drink water", "to study", "to call mom", "to take out the trash",
             "to check the oven", "to stretch my legs", "to submit the form",
             "to water the plants", "to take my medicine", "to feed the cat",
             "to start laundry", "to email the teacher", "to leave for practice",
             "to charge my phone", "to lock the back door", "to review my notes",
             "to attend the meeting", "to pick up the package"]
REM_DELAYS = ["in 5 minutes", "in 10 minutes", "in 15 minutes", "in 20 minutes",
              "in half an hour", "in 45 minutes", "in an hour", "in 2 hours",
              "in 30 seconds", "in one minute", "in 90 minutes", "in three hours"]
JOKES = ["tell me a joke", "make me laugh", "say something funny",
         "got any good jokes", "cheer me up with a joke", "crack a joke",
         "tell me something hilarious", "do your best impression of a comedian",
         "cheer me up", "entertain me for a second"]
GREETINGS = ["good morning", "good evening", "good afternoon", "hello there",
             "hi again", "hey nova", "hello nova", "what's up nova",
             "you there", "good to see you", "welcome back", "long time no see"]
SMALLTALK = ["how are you", "how's your day going", "what's new with you",
             "are you busy right now", "whatcha been up to", "how do you feel",
             "having a good day", "is everything okay", "what are you thinking about",
             "do you ever get bored", "what's on your mind", "how's it going"]
KNOWLEDGE = ["why is the sky blue", "how do magnets work", "why do cats purr",
             "how does photosynthesis work", "what is quantum computing",
             "explain gravity to me", "why is the ocean salty",
             "how do vaccines work", "what causes earthquakes",
             "how does the internet work", "why do we dream",
             "what is machine learning", "how do planes stay in the air",
             "why is venus hotter than mercury", "what is dark matter"]
SEARCH_TOPICS = ["python tutorials", "best laptops 2026", "easy dinner recipes",
                 "beginner guitar lessons", "weather this weekend", "nba scores today",
                 "cheap flights to denver", "how to tie a tie", "history of jazz",
                 "learn spanish fast", "rust vs go", "space news this week",
                 "marathon training plans", "diy shelf ideas", "stock market today"]
WRITING = ["write a short story about a lost dog", "compose a poem about autumn",
           "write an essay on renewable energy", "draft a speech about teamwork",
           "write a paragraph about the ocean", "compose a haiku about rain",
           "write a story about a magic library", "draft a letter to my landlord",
           "write a blog post about coffee", "compose a limerick about work",
           "write a review of a fictional restaurant", "draft an email to my team"]
NOTES_BODY = ["the meeting is at three", "buy milk and eggs", "password reset on friday",
              "idea: mobile app for plants", "call the dentist back", "gym plan: push pull legs",
              "book club on thursday", "wifi password is autumn2026", "draft due monday",
              "car service booked for saturday", "paint the shed in spring",
              "read that article about sleep"]
TYPED = ["hello there", "testing one two three", "great work team",
         "see you tomorrow", "the quick brown fox", "meeting at noon",
         "please print page two", "nova was here", "hello world",
         "urgent: reply today", "thanks for your help", "copy that"]
IG_USERS = ["bestuser123", "photo_fan", "dailygrind", "travelbug", "chefmode",
            "citylights", "naturefeed", "gamerzone", "studynotes", "musicdaily"]


def _variants(templates, slots_per, cap):
    """Fill template families with slot banks; return deduped list."""
    out, seen = [], set()
    for tpl in templates:
        for slots in slots_per:
            s = tpl.format(*slots)
            if s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
    return out[:cap]


def _polite_variants(bases, cap):
    out, seen = [], set()
    i = 0
    # round-robin politeness across bases so each base gets different prefixes
    while len(out) < cap and i < 20:
        for b in bases:
            for p in POLITE[i % len(POLITE):] + POLITE[:i % len(POLITE)]:
                v = f"{p}{b}" if p else b
                if v.lower() not in seen:
                    seen.add(v.lower())
                    out.append(v)
                    if len(out) >= cap:
                        return out
        i += 1
    return out


def build_generators():
    """intent -> callable() -> list of new phrases."""
    g = {}

    def gen_open_app():
        slots = [(a,) for a in APPS] + [("the " + a,) for a in APPS[:6]]
        tpl = ["open {}", "launch {}", "start {}", "fire up {}", "boot up {}",
               "get {} running", "i need {} open", "pull up {}", "run {}",
               "open up {}", "bring up {}", "put {} on"]
        cands = []
        for t in tpl:
            for s in slots:
                cands.append((t.format(*s), t, s))
        return _dedupe_to([c[0] for c in cands], 140)

    def gen_close_app():
        slots = [(a,) for a in APPS] + [("the " + a,) for a in APPS[:6]]
        tpl = ["close {}", "quit {}", "exit {}", "kill {}", "terminate {}",
               "end {}", "shut down {}", "get rid of {}", "stop {}",
               "close down {}", "shut {}", "turn off {}"]
        cands = [t.format(*s) for t in tpl for s in slots]
        return _dedupe_to(cands, 140)

    def gen_open_website():
        slots = [(s,) for s in SITES] + [("the " + s + " website",) for s in SITES[:5]]
        tpl = ["open {}", "go to {}", "visit {}", "launch {}", "take me to {}",
               "navigate to {}", "show me {}", "head over to {}", "pull up {}"]
        cands = [t.format(*s) for t in tpl for s in slots]
        return _dedupe_to(cands, 140)

    def gen_open_tab():
        return _polite_variants([
            "open a new tab", "new tab", "open another tab", "give me a new tab",
            "start a fresh tab", "pop open a new tab", "add a tab",
            "open a tab in the browser", "make a new tab", "one more tab please",
        ], 120)

    def gen_close_tab():
        return _polite_variants([
            "close this tab", "close the current tab", "close the tab",
            "shut this tab", "get rid of this tab", "discard the open tab",
            "close it", "kill this tab", "close the active tab",
            "dismiss this tab", "ditch this tab", "end this tab",
        ], 120)

    def gen_scroll():
        up = _polite_variants([
            "scroll up", "scroll up a bit", "scroll to the top", "go up",
            "scroll back up", "move up the page", "scroll up slowly",
            "head to the top of the page", "page up", "scroll upwards",
        ], 60)
        down = _polite_variants([
            "scroll down", "scroll down a bit", "scroll to the bottom",
            "go down", "keep scrolling down", "scroll further down",
            "move down the page", "head to the bottom", "page down",
            "scroll downwards", "jump to the end of the page",
        ], 60)
        return up + down

    def gen_get_time():
        return _polite_variants([
            "what time is it", "what's the time", "tell me the time",
            "time check", "do you have the time", "what time do you have",
            "current time please", "how late is it", "give me the time",
            "what's the clock say", "time now", "is it late",
        ], 120)

    def gen_reminder():
        cands = []
        for t in REM_TASKS:
            for d in REM_DELAYS:
                cands.append(f"remind me {t} {d}")
                cands.append(f"set a reminder {t} {d}")
        return _dedupe_to(cands, 140)

    def gen_search_web():
        cands = []
        for s in SEARCH_TOPICS:
            cands.append(f"search the web for {s}")
            cands.append(f"search for {s}")
            cands.append(f"look up {s}")
            cands.append(f"google {s}")
            cands.append(f"browse the web for {s}")
            cands.append(f"find information about {s}")
        return _dedupe_to(cands, 140)

    def gen_chat():
        base = GREETINGS + SMALLTALK + JOKES + KNOWLEDGE + WRITING + [
            "what can you do", "who are you", "what's your name",
            "you're doing great", "thanks nova", "thank you",
            "tell me about yourself", "i feel like chatting",
            "give me some motivation", "what should i do today",
        ]
        return _polite_variants(base, 150)

    def gen_get_date():
        return _polite_variants([
            "what's the date", "what is today's date", "what's the date today",
            "tell me the date", "date please", "what is the date",
            "what date is it", "what's today's date", "the date check",
            "what day of the month is it", "current date", "date now",
        ], 120)

    def gen_get_day():
        return _polite_variants([
            "what day is it", "what day is today", "what day are we on",
            "tell me the day", "what's the day today", "which day is it",
            "what day of the week is it", "day check", "is it friday",
            "what weekday are we in", "today's day", "day now",
        ], 120)

    def gen_calculate():
        cands = []
        for a, b, w in CALC_PAIRS:
            cands.append(f"calculate {a} {w} {b}")
            cands.append(f"what is {a} {w} {b}")
            cands.append(f"what's {a} {w} {b}")
        for a, b in CALC_NUMS:
            for w in CALC_WORDS:
                cands.append(f"calculate {a} {w} {b}")
                cands.append(f"what's {a} {w} {b}")
        for p in PCT_PER:
            cands.append(f"what is {p}")
            cands.append(f"calculate {p}")
            cands.append(f"what's {p}")
        for base, exp in POWERS:
            cands.append(f"what is {base} to the power of {exp}")
            cands.append(f"calculate {base} to the power of {exp}")
        for s in SQRTS:
            cands.append(f"calculate {s} square root")
            cands.append(f"what is the square root of {s}")
            cands.append(f"what's the square root of {s}")
        return _dedupe_to(cands, 150)

    def gen_volume_up():
        return _polite_variants([
            "turn the volume up", "volume up", "raise the volume",
            "increase the volume", "make it louder", "it's too quiet",
            "louder please", "crank the volume", "pump up the volume",
            "bring the volume up", "sound is too low", "turn it up",
            "boost the volume", "turn up the sound", "raise the audio",
        ], 120)

    def gen_volume_down():
        return _polite_variants([
            "turn the volume down", "volume down", "lower the volume",
            "decrease the volume", "make it quieter", "it's too loud",
            "quieter please", "bring the volume down", "reduce the volume",
            "the audio is too loud", "turn it down", "tone it down",
            "turn down the sound", "lower the audio", "drop the volume",
        ], 120)

    def gen_set_volume():
        cands = []
        tpl = ["set volume to {}", "set the volume to {} percent",
               "volume to {}", "put the volume at {}", "set volume at {}",
               "set the audio level to {} percent", "make the volume {} percent",
               "volume {} percent", "set my volume to {}", "adjust volume to {} percent"]
        for t in tpl:
            for l in LEVELS:
                cands.append(t.format(l))
        return _dedupe_to(cands, 140)

    def gen_mute():
        return _polite_variants([
            "mute", "mute the volume", "mute the audio", "silence the sound",
            "mute my computer", "mute it please", "turn the sound off",
            "mute the pc", "silence please", "mute the system",
            "put it on mute", "sound off", "mute everything", "silence it",
        ], 120)

    def gen_unmute():
        return _polite_variants([
            "unmute", "unmute the volume", "unmute the audio",
            "turn the sound back on", "unmute my computer",
            "give me sound again", "unmute the system", "turn the mute off",
            "sound on again", "take it off mute", "restore the audio",
            "unmute it", "unmute the machine",
        ], 120)

    def gen_get_volume():
        return _polite_variants([
            "what's the volume", "what is the volume level",
            "how loud is the volume", "volume status",
            "what's the current volume", "check the volume",
            "how high is the sound set", "what's the volume set at",
            "how loud is it set", "check volume level", "current volume please",
            "what level is the sound", "volume level",
        ], 120)

    def gen_brightness_up():
        return _polite_variants([
            "turn the brightness up", "brightness up", "increase the brightness",
            "raise the brightness", "make the screen brighter", "it's too dim",
            "make it brighter", "screen is too dark", "turn up the screen brightness",
            "brighten the screen", "raise the display brightness",
            "brightness higher", "increase screen brightness",
        ], 120)

    def gen_brightness_down():
        return _polite_variants([
            "turn the brightness down", "brightness down",
            "decrease the brightness", "lower the brightness", "dim the screen",
            "make the screen dimmer", "it's too bright", "make it dimmer",
            "screen is too bright at night", "reduce the screen brightness",
            "darken the screen", "turn down the brightness",
            "lower the display brightness", "brightness lower",
        ], 120)

    def gen_set_brightness():
        cands = []
        tpl = ["set brightness to {}", "set the brightness to {} percent",
               "brightness to {}", "set screen brightness to {}",
               "put brightness at {} percent", "set my brightness to {}",
               "brightness {} percent", "adjust brightness to {} percent",
               "set the display brightness to {}", "brightness level {}"]
        for t in tpl:
            for l in LEVELS:
                cands.append(t.format(l))
        return _dedupe_to(cands, 140)

    def gen_battery():
        return _polite_variants([
            "what's my battery percentage", "what is the battery level",
            "how much battery do I have left", "battery status",
            "check the battery", "how is the battery", "battery life",
            "is the battery charging", "how much charge is left",
            "battery percentage please", "battery level check",
            "what is my battery at", "remaining battery power",
            "power level remaining", "battery charge status",
        ], 120)

    def gen_wifi():
        return _polite_variants([
            "wifi status", "what's my wifi connection", "am I connected to wifi",
            "check the wifi", "internet status", "are we connected to the network",
            "what network am I on", "check the internet connection",
            "wifi check please", "what's the wifi status",
            "which wifi network am I on", "check my internet connection",
            "am I on the internet", "network status please",
        ], 120)

    def gen_screenshot():
        return _polite_variants([
            "take a screenshot", "take a screenshot of the screen", "screenshot",
            "capture the screen", "grab a screenshot", "screenshot the display",
            "take a snapshot of my screen", "capture my screen please",
            "screenshot my desktop", "snap a screenshot", "snap the screen",
            "take a screen capture", "capture the display", "grab the screen",
        ], 120)

    def gen_lock():
        return _polite_variants([
            "lock my pc", "lock the computer", "lock my screen",
            "lock the workstation", "lock windows", "lock it",
            "lock my machine", "secure my screen", "lock the pc",
            "lock my desktop", "lock windows now", "lock the machine",
            "lock my computer screen",
        ], 120)

    def gen_shutdown():
        return _polite_variants([
            "shut down my pc", "shut down the computer", "turn off the computer",
            "power off the pc", "shut the machine down", "shutdown",
            "shut down my system", "turn off my computer please",
            "power down the machine", "shut down the pc", "turn off my pc",
            "power off the computer", "shut down windows",
            "turn the machine off", "shut everything down",
        ], 120)

    def gen_restart():
        return _polite_variants([
            "restart my pc", "restart the computer", "reboot the system",
            "reboot my pc", "restart the machine", "restart", "reboot please",
            "restart my computer now", "reboot the computer", "restart the pc",
            "restart windows", "restart this computer", "give it a reboot",
            "reboot my machine",
        ], 120)

    def gen_sleep():
        return _polite_variants([
            "put my pc to sleep", "put the computer to sleep", "sleep the pc",
            "put my computer in sleep mode", "go to sleep mode",
            "make the computer sleep", "sleep my machine",
            "put my computer to sleep", "sleep mode now", "send the pc to sleep",
            "let the computer sleep", "enter sleep mode",
            "put this machine in sleep mode",
        ], 120)

    def gen_play():
        return _polite_variants([
            "play music", "play some music", "play a song", "resume the music",
            "play the track", "play", "put on some music", "start playing music",
            "resume playback", "play my music", "start the music",
            "play a track", "resume my song", "music on", "crank up the tunes",
        ], 120)

    def gen_pause():
        return _polite_variants([
            "pause", "pause the music", "pause the song", "hold on a second",
            "pause playback", "pause it", "stop the music playing",
            "freeze the track", "pause the track", "hold the music",
            "pause it please", "stop playing for a moment",
        ], 120)

    def gen_next():
        return _polite_variants([
            "next track", "next song", "skip this track",
            "skip to the next one", "play the next song", "skip", "next",
            "jump to the next track", "next song please", "skip this song",
            "advance to the next song", "skip forward", "next one",
        ], 120)

    def gen_prev():
        return _polite_variants([
            "previous track", "previous song", "go back a track",
            "play the last song again", "previous", "go back to the previous song",
            "rewind to the last track", "last track", "go to the previous song",
            "play the previous track", "back one song", "skip backward",
            "previous one",
        ], 120)

    def gen_create_folder():
        cands = []
        for f in FOLDERS:
            for tpl in ["create a folder called {}", "make a new folder named {}",
                        "create a folder named {}", "make a folder called {}",
                        "new folder called {}", "create a directory named {}",
                        "make me a folder called {}", "make a directory called {}"]:
                cands.append(tpl.format(f))
        for w in ["desktop", "documents", "downloads"]:
            for f in FOLDERS[:6]:
                cands.append(f"create a folder called {f} on the {w}")
                cands.append(f"make a new folder on the {w} called {f}")
        return _dedupe_to(cands, 140)

    def gen_create_file():
        cands = []
        for f in NOTE_FILES:
            for tpl in ["create a text file called {}", "make a new file named {}",
                        "create a file named {}", "make a text file called {}",
                        "new text file named {}", "create a file called {}",
                        "make me a text file named {}", "create a new file named {}"]:
                cands.append(tpl.format(f))
        return _dedupe_to(cands, 140)

    def gen_open_folder():
        cands = []
        for w in ["downloads", "documents", "desktop", "notes"]:
            for tpl in ["open my {} folder", "open the {} folder", "open {}",
                        "show my {} folder", "launch the {} folder",
                        "open up my {}", "take me to my {}"]:
                cands.append(tpl.format(w))
        return _dedupe_to(cands, 130)

    def gen_list_folder():
        cands = []
        for w in ["downloads", "documents", "desktop", "notes"]:
            for tpl in ["show files in {}", "what's in my {}", "list the files in {}",
                        "what files are in {}", "show what's in {}", "list my {}",
                        "what's inside my {}", "show my {} files"]:
                cands.append(tpl.format(w))
        return _dedupe_to(cands, 130)

    def gen_find_files():
        cands = []
        for w in ["documents", "downloads", "desktop"]:
            for p in FILE_PATS:
                cands.append(f"find my {p} files in {w}")
                cands.append(f"search my {w} for {p} files")
                cands.append(f"find {p} in {w}")
        for p in FILE_PATS:
            cands.append(f"find my {p} files")
            cands.append(f"find {p}")
        return _dedupe_to(cands, 140)

    def gen_rename():
        cands = []
        for a, b in [("draft", "final"), ("notes", "archive"), ("temp", "temp backup"),
                     ("old", "new"), ("report v1", "report v2"), ("photo1", "vacation"),
                     ("essay", "essay final"), ("scan", "invoice scan")]:
            cands.append(f"rename {a} to {b}")
            cands.append(f"rename my file {a} to {b}")
            cands.append(f"rename {a}.txt to {b}.txt in documents")
        return _dedupe_to(cands, 130)

    def gen_move():
        cands = []
        for n in ["report.docx", "homework.txt", "screenshot", "invoice", "presentation",
                  "spreadsheet", "the pdf", "my notes", "the spreadsheet"]:
            for d in ["documents", "downloads", "desktop"]:
                cands.append(f"move {n} to {d}")
        return _dedupe_to(cands, 130)

    def gen_delete():
        cands = []
        for n in ["junk.txt", "old draft", "temp file", "notes file", "backup folder",
                  "test file", "the screenshot", "old notes", "the download"]:
            for w in ["", " from the desktop", " in documents", " from downloads"]:
                cands.append(f"delete {n}{w}")
                cands.append(f"remove {n}{w}")
        return _dedupe_to(cands, 140)

    def gen_list_tasks():
        return _polite_variants([
            "what tasks do I have", "show my tasks", "list my to-dos",
            "what's pending on my list", "which tasks are pending",
            "show my pending tasks", "what's on my task list", "list my tasks",
            "what to-dos are pending", "check my task list", "any tasks pending",
            "show pending tasks", "my tasks please", "task list",
        ], 120)

    def gen_list_reminders():
        return _polite_variants([
            "what reminders do I have", "list my reminders", "show reminders",
            "which reminders are set", "any reminders pending",
            "what reminders are set", "do I have any reminders",
            "show my active reminders", "what have you reminded me about",
            "list pending reminders", "any reminders coming up",
        ], 120)

    def gen_take_note():
        cands = []
        for b in NOTES_BODY:
            for tpl in ["take a note that {}", "note that {}", "write down that {}",
                        "take down {}", "make a note that {}", "jot down that {}"]:
                cands.append(tpl.format(b))
        return _dedupe_to(cands, 130)

    def gen_read_notes():
        return _polite_variants([
            "what's in my notes", "read my notes", "list my notes",
            "read my notes back", "what's in the notebook", "show my notes",
            "read the last note", "what notes do I have", "open my notes",
            "go through my notes", "notes please", "read notes",
        ], 120)

    def gen_click():
        cands = []
        for x in [100, 200, 300, 400, 500, 600, 700, 800]:
            for y in [150, 250, 350, 450, 550, 650]:
                cands.append(f"click at {x}, {y}")
        return _dedupe_to(cands, 120)

    def gen_type():
        cands = []
        for b in TYPED:
            cands.append(f'type "{b}"')
            cands.append(f"type '{b}'")
        return _dedupe_to(cands, 120)

    def gen_instagram():
        cands = []
        for u in IG_USERS:
            cands.append(f"text {u} saying \"Hi\" on instagram")
            cands.append(f'message {u} "Hey!" on instagram')
            cands.append(f"dm {u} on instagram")
        return _dedupe_to(cands, 120)

    def gen_research():
        cands = []
        for t in ["albert einstein", "black holes", "the french revolution",
                  "climate change", "ancient egypt", "the human immune system",
                  "artificial intelligence", "the roman empire", "volcanoes",
                  "the mariana trench", "renewable energy", "blockchain"]:
            cands.append(f"prepare a research document on {t}")
            cands.append(f"make a research paper about {t}")
            cands.append(f"create a research report on {t}")
            cands.append(f"do some research on {t}")
            cands.append(f"compile a research document about {t}")
        return _dedupe_to(cands, 140)

    g.update({
        "OPEN_APP": gen_open_app, "CLOSE_APP": gen_close_app,
        "OPEN_WEBSITE": gen_open_website, "OPEN_TAB": gen_open_tab,
        "CLOSE_TAB": gen_close_tab, "SCROLL": gen_scroll,
        "GET_TIME": gen_get_time, "REMINDER": gen_reminder,
        "SEARCH_WEB": gen_search_web, "CHAT": gen_chat,
        "GET_DATE": gen_get_date, "GET_DAY": gen_get_day,
        "CALCULATE": gen_calculate, "VOLUME_UP": gen_volume_up,
        "VOLUME_DOWN": gen_volume_down, "SET_VOLUME": gen_set_volume,
        "MUTE": gen_mute, "UNMUTE": gen_unmute, "GET_VOLUME": gen_get_volume,
        "BRIGHTNESS_UP": gen_brightness_up, "BRIGHTNESS_DOWN": gen_brightness_down,
        "SET_BRIGHTNESS": gen_set_brightness, "BATTERY_STATUS": gen_battery,
        "WIFI_STATUS": gen_wifi, "SCREENSHOT": gen_screenshot,
        "LOCK_SCREEN": gen_lock, "SHUTDOWN": gen_shutdown, "RESTART": gen_restart,
        "SLEEP_PC": gen_sleep, "PLAY_MUSIC": gen_play, "PAUSE_MUSIC": gen_pause,
        "NEXT_TRACK": gen_next, "PREV_TRACK": gen_prev,
        "CREATE_FOLDER": gen_create_folder, "CREATE_FILE": gen_create_file,
        "OPEN_FOLDER": gen_open_folder, "LIST_FOLDER": gen_list_folder,
        "FIND_FILES": gen_find_files, "RENAME_FILE": gen_rename,
        "MOVE_FILE": gen_move, "DELETE_FILE": gen_delete,
        "LIST_TASKS": gen_list_tasks, "LIST_REMINDERS": gen_list_reminders,
        "TAKE_NOTE": gen_take_note, "READ_NOTES": gen_read_notes,
        "CLICK_AT": gen_click, "TYPE_TEXT": gen_type,
        "INSTAGRAM_DM": gen_instagram, "RESEARCH": gen_research,
    })
    return g


def _dedupe_to(cands, cap):
    seen, out = set(), []
    for c in cands:
        k = c.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(c)
        if len(out) >= cap:
            break
    return out


def main():
    # parse
    sections, cur = [], None
    with open(PHRASES, "r", encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if s.startswith("INTENT:"):
                cur = (s.split("INTENT:")[1].strip(), [])
                sections.append(cur)
            elif cur is not None and s:
                cur[1].append(s[2:] if s.startswith("- ") else s)

    counts = {name: len(lines) for name, lines in sections}
    existing = {l.lower() for _, lines in sections for l in lines}
    index = {name: i for i, (name, _) in enumerate(sections)}

    generators = build_generators()
    added_total = 0
    report = []

    for intent, count in sorted(counts.items(), key=lambda kv: kv[1]):
        if count >= TARGET:
            continue
        gen = generators.get(intent)
        if gen is None:
            report.append(f"  {intent:16} {count:4}  NO GENERATOR — left as is")
            continue
        need = TARGET - count
        cands = [c for c in gen() if c.lower() not in existing]
        picked = cands[:need]
        for p in picked:
            sections[index[intent]][1].append(p)
            existing.add(p.lower())
        added_total += len(picked)
        report.append(f"  {intent:16} {count:4} -> {count + len(picked):4}  (+{len(picked)})")

    with open(PHRASES, "w", encoding="utf-8", newline="\n") as f:
        for name, lines in sections:
            f.write(f"INTENT: {name}\n\n")
            for l in lines:
                f.write(f"- {l}\n")
            f.write("\n")

    print("Scaling report:")
    for r in report:
        print(r)
    print(f"TOTAL ADDED: {added_total}")

    # verify
    final = {}
    cur = None
    for line in open(PHRASES, encoding="utf-8"):
        s = line.strip()
        if s.startswith("INTENT:"):
            cur = s.split(":")[1].strip()
        elif s and cur:
            final[cur] = final.get(cur, 0) + 1
    below = {k: v for k, v in final.items() if v <= 100}
    print(f"\nIntents: {len(final)}, total phrases: {sum(final.values())}")
    print(f"Intents at or below 100: {below if below else 'NONE — requirement met'}")


if __name__ == "__main__":
    main()
