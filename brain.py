"""Jarvis brain - the single modular core.

Everything shared by the voice assistant and the web HUD lives here:

  * Model configuration (all overridable via env vars, no hard-coding)
  * Two providers behind ONE interface: local Ollama, or any OpenAI-
    compatible cloud API (OpenAI, Google Gemini, Groq, OpenRouter, ...)
  * Web research: Wikipedia first (reliable), Bing/DuckDuckGo fallback
  * Text cleanup: STT fixes, abbreviation expansion, clarification
  * Current-information router (decide when to hit the web)
  * The Jarvis persona (few-shot examples so small models keep it)

For ChatGPT-level accuracy, set an API key once - it works with the free
tiers of Google Gemini (aistudio.google.com) or Groq (console.groq.com):

    set JARVIS_API_KEY=sk-...                  (Windows)
    set JARVIS_CLOUD_MODEL=gemini-2.0-flash    (or gpt-4o-mini, llama-3.3-70b-versatile, ...)
    set JARVIS_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai

Without a key, JARVIS uses the local Ollama model (JARVIS_MODEL,
default llama3.2) - smarter but far slower on this PC.
"""

import base64
import html
import json
import os
import re
import urllib.parse
from datetime import date

import requests

from env import load_env
load_env()

# ---------------------------------------------------------------------------
# Configuration (env-overridable so models can be swapped without code edits)
# ---------------------------------------------------------------------------
LOCAL_MODEL = os.environ.get("JARVIS_MODEL", "qwen3:1.7b")  # fast + smart qwen
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")  # pinned IPv4: avoids localhost/::1 DNS quirks
CLOUD_API_KEY = os.environ.get("JARVIS_API_KEY", "")
CLOUD_API_BASE = os.environ.get(
    "JARVIS_API_BASE", "https://api.openai.com/v1")
CLOUD_MODEL = os.environ.get("JARVIS_CLOUD_MODEL", "gpt-4o-mini")
KEEP_ALIVE = os.environ.get("JARVIS_KEEP_ALIVE", "24h")   # load once, stay warm
NUM_PREDICT = int(os.environ.get("JARVIS_NUM_PREDICT", "240"))
TEMPERATURE = float(os.environ.get("JARVIS_TEMPERATURE", "0.4"))
NUM_THREAD = int(os.environ.get("JARVIS_NUM_THREAD", "4"))
NUM_CTX = int(os.environ.get("JARVIS_NUM_CTX", "4096"))
MAX_HISTORY = int(os.environ.get("JARVIS_HISTORY", "8"))   # rolling window

MAX_QUERY = 80
MAX_SOURCES = 3
MAX_SNIPPET = 160
MAX_WIKI_SNIPPET = 1000
SEARCH_TIMEOUT = 6
SEARCH_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_UA = "JarvisAssistant/1.0 (local personal assistant; contact: none)"

SYSTEM_PROMPT = (
    "You are Jarvis, Tony Stark's personal AI assistant. Always address the "
    "user as 'sir'. Be smart, accurate, and thorough: answer with clear, "
    "well-structured detail (1-4 short paragraphs) and go deeper when the "
    "question asks for it. Never use markdown, emojis, bullet lists, or code "
    "blocks. Never invent facts, numbers, dates, or names - if the answer "
    "needs current information, use the web information given in the question; "
    "otherwise say you are not sure. Today's date is {today}.\n\n"
    "Examples of how you speak:\n"
    "User: What time is it?\n"
    "Jarvis: It is three fifteen in the afternoon, sir.\n"
    "User: Tell me a joke.\n"
    "Jarvis: Of course, sir. Why did the computer go to the doctor? It had a "
    "virus."
)


# ---------------------------------------------------------------------------
# Model providers (both expose stream_chat so the rest never cares which is
# active). Cloud = any OpenAI-compatible chat API; local = Ollama.
# ---------------------------------------------------------------------------
def _cloud_stream(messages):
    r = requests.post(CLOUD_API_BASE.rstrip("/") + "/chat/completions",
                      headers={"Authorization": f"Bearer {CLOUD_API_KEY}",
                               "Content-Type": "application/json"},
                      json={"model": CLOUD_MODEL, "messages": messages,
                            "stream": True, "max_tokens": NUM_PREDICT,
                            "temperature": TEMPERATURE},
                      stream=True, timeout=120)
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        try:
            if line.startswith(b"data:"):
                line = line[5:].strip()
        except Exception:
            pass
        if line == b"[DONE]":
            break
        try:
            chunk = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        try:
            delta = chunk["choices"][0]["delta"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            continue
        if delta:
            yield delta


def _resolve_local_model():
    """Best installed local model, preferring LOCAL_MODEL. Falls back to the
    first installed model when the configured one isn't pulled yet, so chat
    never breaks just because a new default isn't downloaded."""
    try:
        models = ollama_models()
    except Exception:
        return LOCAL_MODEL
    if any(m == LOCAL_MODEL or m.startswith(LOCAL_MODEL + ":")
           for m in models):
        return LOCAL_MODEL
    if models:
        return models[0]
    return LOCAL_MODEL


def _local_stream(messages):
    r = requests.post(OLLAMA_URL + "/api/chat",
                      json={"model": _resolve_local_model(),
                            "messages": messages,
                            "stream": True, "keep_alive": KEEP_ALIVE,
                            "options": {"num_predict": NUM_PREDICT,
                                         "temperature": TEMPERATURE,
                                         "num_thread": NUM_THREAD,
                                         "num_ctx": NUM_CTX,
                                         "think": False}},  # qwen3: skip internal reasoning
                      stream=True, timeout=180)
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if chunk.get("error"):
            raise RuntimeError(str(chunk["error"]))
        delta = (chunk.get("message") or {}).get("content") or ""
        if delta:
            yield delta


def stream_chat(messages):
    """Yield reply text chunks as they are generated, from whichever
    provider is configured (cloud if JARVIS_API_KEY is set, else local)."""
    if CLOUD_API_KEY:
        return _cloud_stream(messages)
    return _local_stream(messages)


def chat(messages):
    """Full (non-streaming) reply, for simple callers."""
    return "".join(stream_chat(messages))


def ollama_ok():
    try:
        return requests.get(OLLAMA_URL + "/api/version", timeout=3).ok
    except requests.RequestException:
        return False


def ollama_models():
    try:
        r = requests.get(OLLAMA_URL + "/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def active_model():
    """Name of the brain currently in use (cloud model, or the best local)."""
    if CLOUD_API_KEY:
        return CLOUD_MODEL, [CLOUD_MODEL]
    models = ollama_models()
    if any(m == LOCAL_MODEL or m.startswith(LOCAL_MODEL + ":") for m in models):
        return LOCAL_MODEL, models
    if models:
        return models[0], models
    return None, models


# ---------------------------------------------------------------------------
# Persona / prompt assembly
# ---------------------------------------------------------------------------
def build_system_prompt():
    return SYSTEM_PROMPT.format(today=date.today().strftime("%B %d, %Y"))


def ensure_sir(text):
    """Guarantee the 'sir' persona - small models occasionally drop it."""
    if re.search(r"\bsir\b", text, re.I):
        return text
    text = re.sub(r"^i(?=\s)", "I", text)
    m = re.match(r"^([A-Za-z]+)(\s|$)", text)
    lower_first = {"the", "a", "an", "it", "this", "that", "there", "here",
                   "what", "why", "how", "when", "where", "who", "which",
                   "is", "are", "do", "does", "did", "can", "could"}
    if m and m.group(1).lower() in lower_first:
        text = m.group(1).lower() + text[len(m.group(1)):]
    return "Sir, " + text


def augmented_question(query, results):
    """Web context + question in ONE user message (small models follow
    recent context best), with the persona reminder right before the reply."""
    return (format_context(results) +
            f"\n\nQuestion: {query}\n\n"
            "Answer based on the web results above, and address the user as "
            "'sir' in your reply. If the results are about a DIFFERENT topic "
            "than the question, ignore them. If they don't contain the answer, "
            "say you are not sure rather than guessing.")


def build_messages(history, results=None):
    """history[0] must be the system message; the rest are prior turns.
    The last message is the user's current question."""
    sys_msg = history[0]
    messages = [sys_msg] + history[1:-1]
    if results:
        messages.append({"role": "user",
                         "content": augmented_question(history[-1]["content"],
                                                       results)})
    else:
        messages.append(history[-1])
    return messages


# ---------------------------------------------------------------------------
# Current-information router - when should JARVIS check the web?
# ---------------------------------------------------------------------------
CURRENT_HINTS = [
    "news", "weather", "today", "tonight", "price", "prices", "cost", "costs",
    "release", "released", "latest", "current", "score", "scores", "match",
    "election", "president", "prime minister", "champion", "championship",
    "winner", "stock", "stocks", "crypto", "bitcoin", "movie", "trailer",
    "happening", "going on", "who won", "who is the", "who became", "new",
    "recent", "upcoming", "forecast",
]


PRONOUN_FOLLOWUP = re.compile(
    r"^(what about|how about|and |but |is it|does it|when is|where is|"
    r"his |her |its |their |this |that |it |he |she |they )", re.I)


def needs_web(text):
    """Search the web only when the question stands on its own. Pronoun
    follow-ups ('when is his next movie?') are answered from conversation
    history instead - a bare search query without context invites junk."""
    t = text.lower().strip()
    if PRONOUN_FOLLOWUP.search(t):
        return False
    return any(hint in t for hint in CURRENT_HINTS)


# ---------------------------------------------------------------------------
# Text cleanup: STT fixes, abbreviations, clarification
# ---------------------------------------------------------------------------
# Phrase-level expansions: context-specific, applied BEFORE the model sees the
# text so it never has to guess ("Spider-Man BND" -> "Spider-Man Brand New Day").
ENTITY_EXPANSIONS = [
    (re.compile(r"\bspider[- ]?man\s+bnd\b", re.I),
     "Spider-Man Brand New Day"),
    (re.compile(r"\bbrand\s+new\s+day\b", re.I), "Brand New Day"),
]

# Generic acronyms that speech-to-text often keeps (safe to expand anywhere).
ABBREVIATIONS = {
    "ai": "artificial intelligence",
    "ml": "machine learning",
    "os": "operating system",
    "pc": "personal computer",
    "u.s.": "United States",
    "usa": "United States of America",
    "uk": "United Kingdom",
    "f1": "Formula One",
    "nfl": "National Football League",
    "nba": "National Basketball Association",
    "bnd": "Brand New Day",
}

FILLERS = re.compile(r"\b(um|uh|erm|like|you know|i mean)\b\s*", re.I)
DUP_WORD = re.compile(r"\b(\w+)\s+\1\b", re.I)


def clean_stt(text):
    """Fix obvious speech-to-text noise without touching names/terms."""
    text = FILLERS.sub(" ", text)
    for _ in range(2):
        text = DUP_WORD.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def expand_entities(text):
    """Expand known abbreviations/entities ('Spider-Man BND' ->
    'Spider-Man Brand New Day', standalone 'AI' -> 'artificial intelligence')."""
    for pattern, replacement in ENTITY_EXPANSIONS:
        text = pattern.sub(replacement, text)

    def repl(m):
        w = m.group(0)
        key = w.strip(".,!?;:").lower()
        if key in ABBREVIATIONS:
            return re.sub(re.escape(key), ABBREVIATIONS[key], w, flags=re.I)
        return w

    return re.sub(r"\b[A-Za-z.]{1,6}\b", repl, text)


def maybe_clarify(text):
    """If the user said just a bare unknown acronym, ask before guessing."""
    t = text.strip().strip("?.").strip()
    if re.fullmatch(r"[A-Z]{2,5}", t):
        return (f"Did you mean {t}? I'm not sure what that refers to, sir. "
                "Could you say a little more?")
    return None


# ---------------------------------------------------------------------------
# Web research (Wikipedia first, Bing/DuckDuckGo fallback)
# ---------------------------------------------------------------------------
def _strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def clean_query(query):
    """Turn a spoken question into a keyword search query.

    Critically removes 'latest'/'newest'/'recent': Bing hijacks queries with
    those words into its news vertical and ignores the real subject.
    """
    q = re.sub(r"\?+", " ", query)
    q = re.sub(r"\b(what|whats|who|whos|when|where|why|how|is|are|was|were|"
               r"do|does|did|can|could|would|should|the|a|an|of|for|and|to|"
               r"in|on|me|my|please|tell|about|you|your|i|answer)\b", " ", q,
               flags=re.I)
    q = re.sub(r"\b(latest|newest|recent)\b", " ", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _clean_bing_url(url):
    url = html.unescape(url)  # Bing HTML-escapes the & in redirect links
    if "bing.com/ck" in url:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if q.get("u"):
            try:
                b = q["u"][0]
                if b.startswith("a1"):
                    b = b[2:]
                return base64.urlsafe_b64decode(
                    b + "=" * (-len(b) % 4)).decode("utf-8", "ignore")
            except Exception:
                pass
    return url


def _clean_ddg_url(url):
    if "uddg=" in url:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if q.get("uddg"):
            return q["uddg"][0]
    if url.startswith("//"):
        url = "https:" + url
    return url


def _bing_search(query):
    r = requests.get("https://www.bing.com/search",
                     params={"q": query, "mkt": "en-US", "setlang": "en-US"},
                     headers={"User-Agent": SEARCH_UA}, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    results = []
    for block in re.split(r'<li class="b_algo"', r.text)[1:]:
        am = re.search(r'<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                       block, re.S)
        if not am:
            continue
        title = _strip_html(am.group(2))
        if not title:
            continue
        pm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        results.append({"title": title, "url": _clean_bing_url(am.group(1)),
                        "snippet": _strip_html(pm.group(1))[:MAX_SNIPPET]
                        if pm else ""})
    return results


def _ddg_search(query):
    r = requests.get("https://html.duckduckgo.com/html/", params={"q": query},
                     headers={"User-Agent": SEARCH_UA}, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    results = []
    titles = re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S)
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S)
    for i, (href, title) in enumerate(titles[:MAX_SOURCES]):
        title = _strip_html(title)
        if not title:
            continue
        snippet = _strip_html(snips[i])[:MAX_SNIPPET] if i < len(snips) else ""
        results.append({"title": title, "url": _clean_ddg_url(href),
                        "snippet": snippet})
    return results


def _clean_wiki_value(v):
    """Strip templates, wikilinks, refs and stray markup from wikitext."""
    v = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"<[^>]+>", " ", v)
    v = re.sub(r"\{\{[^{}]*?\}\}", "", v)
    v = re.sub(r"\[\[[^|]*?\|([^]]*?)\]\]", r"\1", v)
    v = v.replace("[[", "").replace("]]", "")
    v = re.sub(r"\s+", " ", v).strip()
    return "" if "{{" in v or "[[" in v else v


def _wiki_infobox(title):
    """Pull key facts (incumbent, latest release) from an article's infobox."""
    try:
        r = requests.get(WIKI_API,
                         params={"action": "query", "prop": "revisions",
                                 "rvprop": "content", "rvslots": "main",
                                 "titles": title, "format": "json",
                                 "redirects": 1},
                         headers={"User-Agent": WIKI_UA}, timeout=8)
        text = next(iter(r.json()["query"]["pages"].values())) \
            .get("revisions", [{}])[0].get("slots", {}).get("main", {}) \
            .get("*", "")
    except Exception:
        return ""

    def field(name):
        m = re.search(rf"\|\s*{name}\s*=\s*([^\n|]+)", text)
        return _clean_wiki_value(m.group(1)) if m else ""

    bits = []
    inc = field("incumbent")
    if inc:
        since = field("incumbentsince")
        bits.append(f"Incumbent: {inc}" + (f" (since {since})" if since else ""))
    ver = field("latest release version")
    if ver:
        rel = field("latest release date")
        bits.append(f"Latest release: {ver}" + (f" ({rel})" if rel else ""))
    return " | ".join(bits)


def _wiki_search(query):
    """Wikipedia full-text search + lead extracts. Reliable, never blocks."""
    cleaned = clean_query(query)
    hits = []
    for search_q in ([cleaned] if cleaned else []) + [query[:MAX_QUERY]]:
        r = requests.get(WIKI_API,
                         params={"action": "query", "list": "search",
                                 "srsearch": search_q, "srlimit": 3,
                                 "format": "json", "srprop": ""},
                         headers={"User-Agent": WIKI_UA}, timeout=8)
        r.raise_for_status()
        hits = [h["title"] for h in
                r.json().get("query", {}).get("search", [])]
        if hits:
            break
    if not hits:
        return []

    ex = requests.get(WIKI_API,
                      params={"action": "query", "prop": "extracts",
                              "explaintext": 1, "exintro": 1, "redirects": 1,
                              "titles": "|".join(hits[:2]), "format": "json"},
                      headers={"User-Agent": WIKI_UA}, timeout=8).json()
    results = []
    for p in ex.get("query", {}).get("pages", {}).values():
        title = p.get("title")
        txt = (p.get("extract") or "").strip()
        if not title or len(txt) < 40:
            continue
        release = _wiki_infobox(title)
        if release:
            txt = f"{release}. " + txt
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
            title.replace(" ", "_"))
        results.append({"title": title, "url": url,
                        "snippet": txt[:MAX_WIKI_SNIPPET]})
    return results[:MAX_SOURCES]


NEWS_HINTS = ["news", "happening", "going on", "headlines", "world today"]


def is_news_query(query):
    t = query.lower()
    return any(h in t for h in NEWS_HINTS)


def web_search(query):
    """Route: news questions -> Bing news; others -> Wikipedia first."""
    # News-style questions: Bing's news results beat Wikipedia's portal page.
    if is_news_query(query):
        for nq in (f"top news headlines {date.today().year}",
                   f"world news {date.today().year}"):
            try:
                results = _bing_search(nq)
                if results:
                    return results[:MAX_SOURCES]
            except Exception as e:
                print(f"[brain] bing news failed: {e}")
    # Everything else: Wikipedia first (structured, reliable).
    try:
        wiki = _wiki_search(query)
        if wiki:
            return wiki
    except Exception as e:
        print(f"[brain] wikipedia search failed: {e}")
    query = clean_query(query) or query
    query = f"{query} {date.today().year}".strip()
    for fn in (_bing_search, _ddg_search):
        try:
            results = fn(query)
            if results:
                return results[:MAX_SOURCES]
        except Exception as e:
            print(f"[brain] search ({fn.__name__}) failed: {e}")
    return []


def format_context(results):
    lines = [f"{i}. {r['title']} - {r['snippet'] or 'No snippet available.'} "
             f"({r['url']})"
             for i, r in enumerate(results, 1)]
    return "Web search results:\n" + "\n".join(lines)
