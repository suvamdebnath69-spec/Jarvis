"""
web.py — everything web-facing NOVA can do.

open_website()   open a known site by spoken name
search_web()     google a query
open_tab()       open a fresh browser tab
close_tab()      send Ctrl+W to the focused window
scroll()         page up / page down on whatever is focused

Tab/scroll control uses WScript.Shell SendKeys (pywin32), so it acts on
the window you're currently using — like Jarvis reaching over your shoulder.
"""

import subprocess
import urllib.parse
import webbrowser

import config


def open_website(site: str):
    url = _resolve_url(site)
    if url is None:
        return "I don't know that site, sir, and I won't open unverified addresses."
    webbrowser.open(url)
    return f"Opening {site}."


def _resolve_url(site: str):
    """Known name -> URL; else validate a bare domain/URL. None = refuse."""
    import re

    site = (site or "").strip().lower()
    if site in config.WEBSITES:
        return config.WEBSITES[site]
    # allow "youtube.com" style bare domains (no scheme, no spaces, sane host)
    if re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[\w./?%&=-]*)?", site):
        return "https://" + site
    return None


def open_website_incognito(site: str):
    """
    Open a site in an Edge InPrivate window (Chrome users: same flag family
    as incognito). Launches its own window via msedge --inprivate so it
    never mixes into the normal session.
    """
    url = config.WEBSITES.get(site) or (
        site if site.startswith("http") else "https://www.google.com/search?q=" + urllib.parse.quote(site)
    )
    exe = _find_edge()
    if exe is None:
        return "I can't find Edge on this machine, sir — InPrivate needs it."
    try:
        subprocess.Popen(
            [exe, "--inprivate", url],
            creationflags=0x00000008,  # DETACHED — outlive the caller
        )
        return f"Opening {site} in an InPrivate window, sir."
    except Exception:
        return f"{site} refused the private window, sir."


def research(topic: str, depth: int = 2):
    """
    Actually research: pull the Wikipedia summary for `topic` plus its
    see-also links, returning raw material NOVA can compose into a
    document. Returns (text, sources) or a persona failure note.
    """
    summary = extract_data(f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(topic)}")
    if summary.startswith(("The web page didn't", "Web extraction", "That page gave")):
        return summary
    extras = []
    try:
        search = extract_data(f"https://en.wikipedia.org/w/index.php?search={urllib.parse.quote(topic)}")
        if not search.startswith(("The web page didn't", "Web extraction", "That page gave")):
            extras.append(search[:800])
    except Exception:
        pass
    parts = [f"RESEARCH: {topic}", "", summary]
    parts.extend(extras[:depth - 1])
    return "\n\n".join(parts)


def search_web(query: str):
    query = _clean_query(query)
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    webbrowser.open(url)
    return f"Searching the web for {query}."


def open_tab():
    # Ctrl+T acts on the browser you're actually using; about:blank popped
    # a whole new window instead of a tab.
    if _send_keys("^t"):
        return "Opened a new tab."
    webbrowser.open("about:blank")
    return "Opened a new browser window."


def close_tab():
    if _send_keys("^w"):
        return "Closing this tab."
    return "I couldn't send the keystroke to your browser."


def scroll(direction: str):
    """up/down page-step; top/bottom jump Home/End (spec §6)."""
    key = {
        "up": "{PGUP}",
        "down": "{PGDN}",
        "top": "{HOME}",
        "bottom": "{END}",
    }.get(direction, "{PGDN}")
    if _send_keys(key):
        label = {
            "up": "Scrolling up.",
            "down": "Scrolling down.",
            "top": "At the top of the page, sir.",
            "bottom": "At the bottom of the page, sir.",
        }.get(direction, "Scrolling.")
        return label
    return "I couldn't send the keystroke — click on the page first."


# ------------------------------------------------------------------ helpers ----

def _clean_query(text: str) -> str:
    """Strip command words so the query is just the thing being searched."""
    import re

    text = re.sub(
        r"^(please\s+)?(can you\s+)?(search|look ?up|google|find)( the web| online| for| about| this| it| me)?\s*",
        "", text, flags=re.I,
    ).strip(" ?.!")
    return text or "python"


def _send_keys(keys: str) -> bool:
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys(keys)
        return True
    except Exception:
        return False


def _find_edge():
    import shutil

    exe = shutil.which("msedge")
    if exe:
        return exe
    for path in config.EDGE_PATHS:
        import os

        if os.path.exists(path):
            return path
    return None


def extract_data(url: str, selector: str = ""):
    """
    Pull readable text out of a webpage (requests + BeautifulSoup).
    Optional CSS selector narrows what's returned. Returns a string —
    either extracted text (capped) or a composed-in-persona failure note.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return "Web extraction needs the requests and beautifulsoup4 packages, sir."
    try:
        if not url.startswith("http"):
            url = "https://" + url
        response = requests.get(
            url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        soup = BeautifulSoup(response.text, "html.parser")
        if selector:
            parts = [el.get_text(" ", strip=True) for el in soup.select(selector)[:20]]
        else:
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            parts = [soup.get_text(" ", strip=True)]
        text = " ".join(parts).strip()
        if not text:
            return "That page gave me nothing readable, sir."
        return text[:1200]
    except Exception as e:
        return f"The web page didn't cooperate, sir: {e}"
