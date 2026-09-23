"""
fast_path.py — how NOVA understands you.

Three-stage understanding, local-first:

  1. Rule layer  — precise regex patterns with parameter capture
                   ("open spotify", "set volume to 40", "remind me to eat
                   in 10 minutes"). Instant, exact, no neural net needed.
  2. Neural path — the trained intent_classifier network for everything
                   the rules don't catch (fuzzy phrasing, novel sentences).
  3. Fallback    — (None, low confidence) -> main.py routes to the LLM.

The rules return (intent, params). The neural path returns (intent,
confidence) + best-effort parameter extraction. Local intents NEVER pay
LLM latency.
"""

import json
import os
import re

import numpy as np

import config

# ------------------------------------------------------------- load model ----
_VOCAB_PATH = os.path.join(config.INTENT_DIR, "vocab.json")
_INTENTS_PATH = os.path.join(config.INTENT_DIR, "intents.json")
_WEIGHTS_PATH = os.path.join(config.INTENT_DIR, "model_weights.npz")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _tokenize(text):
    return re.findall(r"[a-z']+", text.lower().replace("\u2019", "'"))


def _vectorize(text, vocab):
    vec = np.zeros(len(vocab))
    for word in _tokenize(text):
        if word in vocab:
            vec[vocab[word]] = 1.0
    return vec


def _softmax(z):
    z = z - np.max(z)
    e = np.exp(z)
    return e / np.sum(e)


class FastPath:
    def __init__(self):
        self.vocab = _load_json(_VOCAB_PATH)
        idx_to_intent = _load_json(_INTENTS_PATH)
        self.idx_to_intent = {int(k): v for k, v in idx_to_intent.items()}

        data = np.load(_WEIGHTS_PATH)
        self.W1, self.b1 = data["W1"], data["b1"]
        self.W2, self.b2 = data["W2"], data["b2"]

        # sanity: the checkpoint must match the current vocab
        if self.W1.shape[0] != len(self.vocab):
            raise RuntimeError(
                "model_weights.npz doesn't match vocab.json — run train.py"
            )

    # ---------------------------------------------------------- neural net ----
    def neural_classify(self, text):
        """Returns (intent, confidence). Pure forward pass, no rules."""
        a1 = np.maximum(0, _vectorize(text, self.vocab) @ self.W1 + self.b1)
        probs = _softmax(a1 @ self.W2 + self.b2)
        idx = int(np.argmax(probs))
        return self.idx_to_intent[idx], float(probs[idx])

    # ------------------------------------------------------------ rules ----
    # Each rule: (compiled regex, intent name). Rules run before the neural
    # net so precise commands with parameters never pay model latency.
    # ORDER MATTERS: specific rules must sit above generic open/close verbs.

    # polite prefixes tolerated before exact keywords ("please", "nova,")
    _POLITE = r"^(?:please\s+|nova[\s,]+|(?:can|could)\s+you\s+)*"

    _NUM = r"(\d+(?:\.\d+)?)"   # plain capture — extract digits in handlers

    _RULES = [
        # --- beast mode (a toggle state, not a program) ---
        # Arming keyword is exactly "enter beast mode" — nothing looser.
        (
            re.compile(_POLITE + r"enter\s+(?:the\s+)?beast(\s*mode)?\b", re.I),
            "BEAST_ON",
        ),
        # Disarming keyword is exactly "come back to normal mode".
        (
            re.compile(
                _POLITE + r"come\s+back\s+to\s+(?:the\s+)?normal(\s*mode)?\b"
                r"|" + _POLITE + r"go\s+back\s+to\s+(?:the\s+)?normal(\s*mode)?\b",
                re.I,
            ),
            "BEAST_OFF",
        ),
        (
            re.compile(
                _POLITE + r"(?:exit|leave)\s+(?:the\s+)?beast(\s*mode)?\b"
                r"|" + _POLITE + r"stand\s+down\b",
                re.I,
            ),
            "BEAST_OFF",
        ),
        # --- confirm / cancel a pending dangerous action ---
        (
            re.compile(r"^\s*(?:confirm|confirmed|yes,\s*do it|do it|go ahead)\b", re.I),
            "CONFIRM",
        ),
        (
            re.compile(r"^\s*(?:cancel|never\s?mind|abort|don'?t do it|no,?\s+(?:stop|cancel|don'?t))\b", re.I),
            "CANCEL",
        ),
        # --- notes (rule-only intents, not part of the neural set) ---
        (
            re.compile(
                r"\b(?:take|write)\s+down\s+(?P<body>.+)"
                r"|\b(?:take|make|write)\s+a\s+note\s+(?:about\s+|on\s+|that\s+)?(?P<body2>.+)"
                r"|\bnote\s+(?:that\s+)?(?P<body3>.+)",
                re.I,
            ),
            "TAKE_NOTE",
        ),
        (
            re.compile(
                r"\b(?:what(?:'s| is)? (?:in )?my notes|read (?:my )?notes?|list (?:my )?notes?)\b",
                re.I,
            ),
            "READ_NOTES",
        ),
        # --- reminders (capture task text + delay) ---
        (
            re.compile(
                r"\b(?:remind me(?: to| about)?|set (?:a|an) reminder (?:for|to|about)?)\s+(?P<task>.+?)"
                r"(?:\s+(?:in|after)\s+(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>minutes?|mins?|hours?|hrs?|h\b|min\b|seconds?|secs?))?\s*[.?!]?\s*$",
                re.I,
            ),
            "REMINDER",
        ),
        (
            re.compile(
                r"\b(?:what|which) reminders? (?:do i have|are (?:set|pending|active))\b"
                r"|\b(?:list|show|any)\s+reminders?\b",
                re.I,
            ),
            "LIST_REMINDERS",
        ),
        # --- calculator (before open/close verbs — text is parsed later) ---
        (
            re.compile(
                r"^(?:hey\s+)?(?:nova[\s,]+)?(?:please\s+)?"
                r"(?:calculate|compute|solve)\s+(?P<expr>.+)"
                r"|^(?:what(?:'s| is)|whats|how much is)\s+[\d(]",
                re.I,
            ),
            "CALCULATE",
        ),
        # --- date / day / time (before generic question routing) ---
        (
            re.compile(
                r"\bwhat(?:'s| is)? (?:the )?date(?: today| today's)?\b"
                r"|\bwhat(?:'s| is)? today'?s date\b"
                r"|\btell me the (?:current )?date\b"
                r"|\bdate (?:please|check|now)\b",
                re.I,
            ),
            "GET_DATE",
        ),
        (
            re.compile(
                r"\bwhat day (?:is it|is today|are we on)\b"
                r"|\bwhat'?s (?:the )?day today\b"
                r"|\btell me the day\b",
                re.I,
            ),
            "GET_DAY",
        ),
        (
            re.compile(r"\b(?:what(?:'s| is)? the time|what time is it|time(?: check| now| please)?)\b", re.I),
            "GET_TIME",
        ),
        # --- system control ---
        (
            re.compile(
                r"\b(?:set|put)\s+(?:the\s+)?volume\s+(?:to|at)\s+" + _NUM + r"\s*(?:%|percent)?\b"
                r"|\bvolume\s+(?:to|at)\s+" + _NUM + r"\s*(?:%|percent)?\b",
                re.I,
            ),
            "SET_VOLUME",
        ),
        (
            re.compile(
                r"\b(?:turn|crank|pump|bring)\s+(?:the\s+)?volume\s+up\b"
                r"|\b(?:increase|raise)\s+(?:the\s+)?volume\b"
                r"|\bvolume\s+up\b"
                r"|\b(?:make it|turn it)\s+louder\b"
                r"|\bit'?s too quiet\b"
                r"|\blouder\b",
                re.I,
            ),
            "VOLUME_UP",
        ),
        (
            re.compile(
                r"\b(?:turn|bring)\s+(?:the\s+)?volume\s+down\b"
                r"|\b(?:decrease|lower|reduce)\s+(?:the\s+)?volume\b"
                r"|\bvolume\s+down\b"
                r"|\b(?:make it|turn it)\s+quieter\b"
                r"|\bit'?s too loud\b"
                r"|\bquieter\b",
                re.I,
            ),
            "VOLUME_DOWN",
        ),
        (
            re.compile(
                r"\b(?:mute|silence)\b(?:\s+(?:the\s+)?(?:volume|audio|sound|pc|computer))?"
                r"|\bmute\s+it\b",
                re.I,
            ),
            "MUTE",
        ),
        (
            re.compile(r"\b(?:unmute)\b(?:\s+(?:the\s+)?(?:volume|audio|sound))?", re.I),
            "UNMUTE",
        ),
        (
            re.compile(
                r"\b(?:what(?:'s| is)? the volume|how (?:loud|high) is the volume|volume (?:level|status)?)\b",
                re.I,
            ),
            "GET_VOLUME",
        ),
        (
            re.compile(
                r"\b(?:turn|crank)\s+(?:the\s+)?brightness\s+up\b"
                r"|\b(?:increase|raise)\s+(?:the\s+)?brightness\b"
                r"|\bbrightness\s+up\b"
                r"|\b(?:make it|it'?s too)\s+bright(er)?\b"
                r"|\bmake the screen brighter\b",
                re.I,
            ),
            "BRIGHTNESS_UP",
        ),
        (
            re.compile(
                r"\b(?:turn|bring)\s+(?:the\s+)?brightness\s+down\b"
                r"|\b(?:decrease|lower|reduce|dim)\s+(?:the\s+)?brightness\b"
                r"|\bbrightness\s+down\b"
                r"|\b(?:make it|it'?s too)\s+dim\b"
                r"|\bmake the screen dimmer\b",
                re.I,
            ),
            "BRIGHTNESS_DOWN",
        ),
        (
            re.compile(
                r"\b(?:set\s+)?brightness\s+(?:to|at)\s+" + _NUM + r"\s*(?:%|percent)?\b",
                re.I,
            ),
            "SET_BRIGHTNESS",
        ),
        (
            re.compile(
                r"\b(?:how much )?batter(?:y|ies)\b.{0,30}?\b(?:percentage|percent|level|left|status|life)\b"
                r"|\bbattery\s+(?:percentage|percent|level|status|life)\b"
                r"|\bhow(?:'s| is) (?:the|my) battery\b"
                r"|\bcheck (?:the )?battery\b",
                re.I,
            ),
            "BATTERY_STATUS",
        ),
        (
            re.compile(
                r"\bwi-?fi\s+(?:status|check|connection|network)\b"
                r"|\b(?:am i|are we) (?:connected to|on) (?:wi-?fi|the internet|the network)\b"
                r"|\bcheck (?:the )?wi-?fi\b"
                r"|\binternet (?:status|connection|check)\b",
                re.I,
            ),
            "WIFI_STATUS",
        ),
        (
            re.compile(
                r"\btake\s+(?:a\s+)?screenshot\b|\bscreenshot\b|\bcapture (?:the )?screen\b",
                re.I,
            ),
            "SCREENSHOT",
        ),
        (
            re.compile(
                r"\block\s+(?:my|the|this)?\s*(?:pc|computer|screen|workstation|windows)\b"
                r"|\block\s+it\b",
                re.I,
            ),
            "LOCK_SCREEN",
        ),
        # --- dangerous power actions (require confirmation) ---
        # 'pc|computer|machine|system|windows' required so "shut down
        # chrome" stays a CLOSE_APP.
        (
            re.compile(
                r"\b(?:shut\s+(?:down|off)|turn\s+off|power\s+off)\s+(?:the|my|this)?\s*(?:pc|computer|machine|system|windows)\b"
                r"|\bshut\s+down\b\s*$"
                r"|\bshutdown\b\s*$",
                re.I,
            ),
            "SHUTDOWN",
        ),
        (
            re.compile(
                r"\b(?:restart|reboot)\s+(?:the|my|this)?\s*(?:pc|computer|machine|system|windows)\b"
                r"|\b(?:restart|reboot)\b\s*$",
                re.I,
            ),
            "RESTART",
        ),
        (
            re.compile(
                r"\b(?:put\s+(?:the|my|this)?\s*(?:pc|computer|machine|system)?\s*to\s+sleep|sleep\s+(?:the|my)?\s*(?:pc|computer|machine)|go\s+to\s+sleep)\b",
                re.I,
            ),
            "SLEEP_PC",
        ),
        # --- media keys ---
        (
            re.compile(
                r"\b(?:play|resume)\s+(?:some\s+|the\s+)?music\b"
                r"|\bplay\s+(?:a\s+)?(?:song|track)\b"
                r"|\b(?:play|resume)\s+it\b"
                r"|\bplay\b\s*$",
                re.I,
            ),
            "PLAY_MUSIC",
        ),
        (
            re.compile(r"\b(?:pause|hold on)\b(?:\s+(?:the\s+)?music)?", re.I),
            "PAUSE_MUSIC",
        ),
        (
            re.compile(
                r"\b(?:next|skip)\s+(?:song|track|one)?\b"
                r"|\bskip\s+(?:this|it)\b"
                r"|\bnext\b\s*$",
                re.I,
            ),
            "NEXT_TRACK",
        ),
        (
            re.compile(
                r"\b(?:previous|last|prior)\s+(?:song|track|one)?\b"
                r"|\bgo\s+back\s+a\s+(?:song|track)\b"
                r"|\bprevious\b\s*$",
                re.I,
            ),
            "PREV_TRACK",
        ),
        # --- files & folders (before OPEN_APP so "open downloads" works) ---
        (
            re.compile(
                r"\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory|dir)\s+on\s+(?:the\s+)?(?:my\s+)?(?P<where3>desktop|documents|downloads)\b"
                r"|\bcreate\s+(?:a\s+)?(?:new\s+)?(?:folder|directory|dir)\s+(?:called\s+|named\s+)?(?P<name>[^.,!?]+)"
                r"|\bmake\s+(?:a\s+)?(?:new\s+)?(?:folder|directory|dir)\s+(?:called\s+|named\s+)?(?P<name2>[^.,!?]+)",
                re.I,
            ),
            "CREATE_FOLDER",
        ),
        (
            re.compile(
                r"\bcreate\s+(?:a\s+)?(?:new\s+)?(?:text\s+)?file\s+(?:called\s+|named\s+)?(?P<name>[^.,!?]+)",
                re.I,
            ),
            "CREATE_FILE",
        ),
        (
            re.compile(
                r"\b(?:open|show|launch)\s+(?:my\s+|the\s+)?(?P<where>desktop|documents|downloads|notes)\s*(?:folder|directory|files)?\b",
                re.I,
            ),
            "OPEN_FOLDER",
        ),
        (
            re.compile(
                r"\b(?:show|list|what(?:'s| is)? in)\s+(?:my\s+|the\s+)?(?P<where>desktop|documents|downloads|notes)\b"
                r"|\bwhat files\s+(?:do i have|are there)\s+(?:in\s+)?(?P<where2>desktop|documents|downloads)?\b",
                re.I,
            ),
            "LIST_FOLDER",
        ),
        (
            re.compile(
                r"\b(?:find|search)\s+(?:my\s+|for\s+)?(?P<pat>[\w\-. ]+?)\s+(?:files?|in)\s+(?:in\s+)?(?P<where>desktop|documents|downloads|notes)\b"
                r"|\bfind\s+(?:my\s+|for\s+)?(?P<pat2>[\w\-. ]+?)\s+files?\b"
                r"|\bsearch\s+(?:my\s+|the\s+)?(?P<where2>desktop|documents|downloads|notes)\s+for\s+(?P<pat3>[\w\-. ]+?)\s*[.?!]?\s*$",
                re.I,
            ),
            "FIND_FILES",
        ),
        (
            re.compile(
                r"\brename\s+(?P<old>[\w\-. ]+?)\s+to\s+(?P<new>[\w\-. ]+?)\s*(?:in\s+(?P<where>desktop|documents|downloads))?\s*[.?!]?\s*$",
                re.I,
            ),
            "RENAME_FILE",
        ),
        (
            re.compile(
                r"\bmove\s+(?P<name>[\w\-. ]+?)\s+to\s+(?:my\s+|the\s+)?(?P<dest>desktop|documents|downloads|notes)\b",
                re.I,
            ),
            "MOVE_FILE",
        ),
        (
            re.compile(
                r"\b(?:delete|remove)\s+(?:the\s+)?(?:file\s+|folder\s+)?(?P<name>[\w\-. ]+?)"
                r"(?:\s+(?:in|from)\s+(?:the\s+)?(?P<where>desktop|documents|downloads|notes))?\s*[.?!]?\s*$",
                re.I,
            ),
            "DELETE_FILE",
        ),
        (
            re.compile(
                r"\b(?:what|which)\s+(?:tasks?|to-?dos?)\s+(?:do i have|are pending|are on my list)\b"
                r"|\b(?:show|list)\s+(?:my\s+)?(?:tasks?|to-?dos?|pending tasks?)\b",
                re.I,
            ),
            "LIST_TASKS",
        ),
        # --- web search (explicit request only) ---
        (
            re.compile(
                r"\b(?:search (?:the web |online |google )?(?:for|about)|look ?up|google|find(?: me)? (?:info(?:rmation)? )?(?:about|on))\s+(?P<query>.+?)\s*[.?!]?\s*$",
                re.I,
            ),
            "SEARCH_WEB",
        ),
        # --- research + document ---
        (
            re.compile(
                r"\b(?:prepare|make|create|write|compile|put together|do)\s+(?:a|an|some)\s+"
                r"(?:(?:small|quick|brief|detailed)\s+)?research(?:\s+(?:paper|doc(?:ument)?|report|notes?))?"
                r"(?:\s+(?:about|on|for|regarding|into))\s+(?P<topic>.+?)\s*[.?!]?\s*$"
                r"|\bresearch\s+(?P<topic2>.+?)\s+(?:and\s+)?(?:make|write|prepare|create)\s+(?:a|an)\s+doc(?:ument)?\b\s*[.?!]?\s*$",
                re.I,
            ),
            "RESEARCH",
        ),
        # --- private/incognito website ---
        (
            re.compile(
                r"\b(?:open|visit|launch|go to)\s+(?P<site>[a-z0-9 .]+?)\s+"
                r"(?:in\s+)?(?P<private>incognito|inprivate|privately|private(?:\s+browsing|\s+mode)?|guest\s+mode)\b"
                r"|\b(?:open|visit|launch|go to)\s+(?P<private2>incognito|inprivate|private)\s+(?P<site2>[a-z0-9 .]+?)\s*[.?!]?\s*$",
                re.I,
            ),
            "OPEN_WEBSITE",
        ),
        # --- click / type (beast mode) ---
        (
            re.compile(
                r"\bclick\s+(?:on\s+)?(?:at\s+)?(?:the\s+)?(?:screen|point)?\s*"
                r"(?:\((?P<x>\d+)\s*[, ]\s*(?P<y>\d+)\))?",
                re.I,
            ),
            "CLICK_AT",
        ),
        (
            re.compile(
                r"\btype\s+(?P<body>\"[^\"]+\"|'[^']+')",
                re.I,
            ),
            "TYPE_TEXT",
        ),
        (
            re.compile(
                r"\b(?:text|message|dm)\s+(?:user\s+)?(?P<user>[a-z0-9._]+)\s+(?:saying\s+|that\s+|with\s+|write\s+)?(?P<msg>\"[^\"]+\"|'[^']+')\s+on\s+(?:instagram|insta)\b"
                r"|\b(?:text|message|dm)\s+(?P<user2>[a-z0-9._]+)\s+on\s+(?:instagram|insta)\b",
                re.I,
            ),
            "INSTAGRAM_DM",
        ),
        # --- known websites (before open app: "open youtube" is a site) ---
        (
            re.compile(
                r"\b(?:open|go to|visit|launch|take me to|navigate to)\s+(?P<site>[a-z0-9 .]+?)\s*(?:website|site|\.com|page)?\s*[.?!]?\s*$",
                re.I,
            ),
            "OPEN_WEBSITE",
        ),
        # --- open app ---
        (
            re.compile(
                r"\b(?:open|launch|start|fire up|boot(?: up)?|get)\s+(?:(?:the|my|a)\s+)?(?P<app>[a-z0-9+ .]+?)\s*(?:app|application|program|browser|for me|please)?\s*[.?!]?\s*$",
                re.I,
            ),
            "OPEN_APP",
        ),
        # --- close app ---
        (
            re.compile(
                r"\b(?:close|quit|exit|kill|shut(?: down)?|stop|terminate|end)\s+(?:(?:the|my|this|running)\s+)?(?P<app>[a-z0-9+ .]+?)\s*(?:app|application|program|browser|window|process|please|completely|for me)?\s*[.?!]?\s*$",
                re.I,
            ),
            "CLOSE_APP",
        ),
    ]

    def rule_classify(self, text):
        """Returns (intent, params) or (None, None) if no rule matches."""
        text = text.strip()
        for pattern, intent in self._RULES:
            m = pattern.match(text)
            if not m:
                continue
            params = m.groupdict() if m.groups() else {}

            if intent == "OPEN_WEBSITE":
                site = (params.get("site") or params.get("site2") or "").strip().lower().strip()
                private = bool(params.get("private") or params.get("private2"))
                if site in config.WEBSITES or private:
                    return intent, {"site": site, "private": private}
                continue  # not a known site — let the neural path decide

            if intent == "OPEN_APP":
                app = (params.get("app") or "").strip().lower()
                if app in config.APP_COMMANDS:
                    return intent, {"app": app}
                continue  # unknown app name — maybe it's a website or chatter

            if intent == "CLOSE_APP":
                app = (params.get("app") or "").strip().lower()
                if app in config.APP_PROCESSES:
                    return intent, {"app": app}
                continue

            return intent, params
        return None, None

    # ------------------------------------------------ parameter extraction ----
    def _neural_params(self, text, intent):
        """Best-effort local parameter extraction for neural-routed intents."""
        params = {}
        if intent == "REMINDER":
            params["task"] = text
        elif intent == "SEARCH_WEB":
            params["query"] = text
        elif intent == "RESEARCH":
            m = re.search(
                r"(?:about|on|for|regarding|into)\s+(.+?)\s*[.?!]?$", text, re.I
            )
            if m:
                params["topic"] = m.group(1)
        elif intent == "SET_VOLUME":
            m = re.search(r"(\d+)", text)
            if m:
                params["level"] = int(m.group(1))
        elif intent == "SET_BRIGHTNESS":
            m = re.search(r"(\d+)", text)
            if m:
                params["level"] = int(m.group(1))
        elif intent in ("CALCULATE",):
            params["expr"] = text
        elif intent in ("CLICK_AT",):
            m = re.search(r"(\d+)\s*[, ]\s*(\d+)", text)
            if m:
                params.update({"x": int(m.group(1)), "y": int(m.group(2))})
        elif intent == "OPEN_WEBSITE":
            for name in config.WEBSITES:
                if re.search(rf"\b{re.escape(name)}\b", text, re.I):
                    params["site"] = name
                    break
        elif intent in ("OPEN_APP", "CLOSE_APP"):
            for name in config.APP_COMMANDS:
                if re.search(rf"\b{re.escape(name)}\b", text, re.I):
                    params["app"] = name
                    break
        return params

    # ------------------------------------------------------------- public ----
    def understand(self, text):
        """
        Full pipeline: rules first, neural net second.
        Returns dict(intent, params, confidence, source).
        """
        intent, params = self.rule_classify(text)
        if intent:
            return {
                "intent": intent,
                "params": params or {},
                "confidence": 1.0,
                "source": "rule",
            }

        intent, confidence = self.neural_classify(text)
        params = self._neural_params(text, intent)
        return {
            "intent": intent,
            "params": params,
            "confidence": confidence,
            "source": "neural",
        }

    def classify(self, text):
        """Convenience wrapper: (intent, confidence) for the whole pipeline."""
        u = self.understand(text)
        return u["intent"], u["confidence"]


# shared instance
fast_path = FastPath()
