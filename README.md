# J.A.R.V.I.S. — your Iron Man assistant

A voice assistant that runs **entirely locally** on your PC. At login it starts
by itself, greets you aloud — *"Welcome back, sir! How can I help you?"* — and
answers your spoken questions with a local Ollama model. Every answer is backed
by a quick web search, so Jarvis knows things newer than his training data.
No browser, no API keys, no cloud LLM.

```
Your voice ──► speech-to-text ──► web search (Bing) ──► local Ollama model ──► spoken reply
```

## How it works

Two programs share one modular core:

| File | What it does |
| --- | --- |
| **`brain.py`** | The brain: model config, streaming provider (cloud or Ollama), web research (Wikipedia → Bing), text cleanup, abbreviation expansion, the "sir" persona. Swap models by editing its env vars — nothing else changes. |
| **`voice.py`** | Conversational TTS: **ElevenLabs** when a key is set (defaults to the iconic JARVIS voice), else **edge-tts** (free, `JARVIS_VOICE`); pyttsx3 offline fallback. Streams chunks through pygame so Jarvis speaks while the model still generates. |
| **`assistant.py`** | The headless voice assistant. Boots silently at login, greets you aloud, listens for *"Hey Jarvis, …"*, streams replies chunk-by-chunk so it starts speaking before the answer is done. **This is the one that auto-starts.** |
| **`server.py`** | Optional: serves the animated **J.A.R.V.I.S. HUD** at `http://127.0.0.1:8420`. Run `python server.py` for the visual. |

Both the voice assistant and the HUD share the same brain, persona, and web
research. Jarvis only searches the web when a question needs current
information (news, releases, weather, prices, people in office, sports...);
conversation and follow-ups are answered from memory.

## First-time setup

1. **Ollama** — install from <https://ollama.com/download> and start it
   (it runs in your system tray).
2. **Pull a model**:

   ```
   ollama pull llama3.2
   ```

   `llama3.2` (3B) is the default local brain — accurate but slow on weak PCs
   (~45-90s per researched answer). For fast, ChatGPT-level answers, add a
   **free cloud key** (see below) and Jarvis uses that automatically.
3. **Python deps**:

   ```
   pip install SpeechRecognition pyttsx3 sounddevice requests edge-tts pygame keyboard
   ```

4. **Test it**:

   ```
   python assistant.py --test
   ```

5. **Run it** (or reboot — it's already set to start automatically):

   ```
   python assistant.py
   ```

   Then say: *"Hey Jarvis, what's the latest version of Windows?"*

## Give Jarvis the ElevenLabs conversational voice

By default Jarvis uses a free neural voice (Edge). For the iconic,
conversational JARVIS voice, add a free ElevenLabs key:

```
set ELEVENLABS_API_KEY=your_key_here
set ELEVENLABS_VOICE=JBF_dEiPT3w5jBBS5k4kY   (the JARVIS voice; change to any voice id)
set ELEVENLABS_MODEL=eleven_turbo_v2_5        (lowest latency)
```

Get a free key at <https://elevenlabs.io>. With the key set, every spoken
reply uses ElevenLabs; if the key is missing or the API errors, Jarvis falls
back to the Edge voice automatically.

## Give Jarvis a ChatGPT-level brain (cloud)

The local 3B model is as smart as this PC's 2-core CPU can run. For truly
smart, fast, detailed answers, plug in any OpenAI-compatible API — free tiers
work. Two easy options:

**Google Gemini (free key):** go to <https://aistudio.google.com/apikey>,
create a key, then:

```
set JARVIS_API_KEY=AIza...
set JARVIS_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai
set JARVIS_CLOUD_MODEL=gemini-2.0-flash
```

**Groq (free key):** go to <https://console.groq.com/keys>, create a key, then:

```
set JARVIS_API_KEY=gsk_...
set JARVIS_API_BASE=https://api.groq.com/openai/v1
set JARVIS_CLOUD_MODEL=llama-3.3-70b-versatile
```

Once `JARVIS_API_KEY` is set, both the voice assistant and the HUD use the
cloud brain (fast, detailed, accurate) and skip the local model entirely.
Unset the variable to go back to local.

## Start automatically at login

Already installed (`jarvis_startup.vbs` in your Windows Startup folder). It
launches `assistant.py` silently with **no browser and no window**. You can
re-register or remove it anytime:

```
python assistant.py --install
python assistant.py --remove
```

The first time after boot, Jarvis says *"Welcome back, sir! How can I help you?"*
and starts listening. (If you'd rather boot into the visual HUD instead, run
`python server.py --install` — both write the same startup entry, so the last
one installed wins.)

## Talking to Jarvis

- Say **"Hey Jarvis"** followed by your question: *"Hey Jarvis, who won the last
  World Cup?"*
- Say just **"Hey Jarvis"** and he replies *"Welcome back, sir! How can I help
  you?"*
- **"exit"**, **"goodbye"**, or **"go to sleep"** makes him stop.
- **"what can you do"** gets a quick help prompt.

### Keyboard wake — no mic needed

Press **`Ctrl+Alt+J`** anytime and Jarvis:

1. **Pops up the HUD** in your browser (starts the server if it isn't running)
   so you can type your command,
2. then says *"Yes, sir?"* and listens for a spoken command if a mic is
   available.

The hotkey works even when you're not using the wake word. Change it with the
`JARVIS_HOTKEY` env var (e.g. `set JARVIS_HOTKEY=ctrl+shift+j`).

### Web research

Before every answer, Jarvis searches the web (Bing, no API key needed) and feeds
the top results to the model as context, so answers stay current. Watch
`assistant.log` or the HUD's activity log for "web scan complete — N sources".
If the search is unreachable, he answers from the model's own knowledge.

## Customizing

Everything is in the `Configuration` block at the top of `assistant.py`
(`server.py` mirrors it):

- `NAME` / `WAKE_PHRASES` — the name and wake words Jarvis answers to
- `MODEL` — default Ollama model (`qwen3:1.7b` — fast + smart; `qwen2.5:1.5b` for max speed, `llama3.2` for quality)
- `SYSTEM_PROMPT` — his personality ("address the user as sir", keep it short)
- `NUM_PREDICT` — reply length cap (keeps answers snappy on slow CPUs)

Use `--model` at runtime: `python assistant.py --model llama3.2`.

## Speed notes

On this PC (2-core CPU), the 3B `llama3.2` model takes ~40-60s per answer.
The default `qwen3:1.7b` is a good middle ground — smarter than `qwen2.5:1.5b`
and faster than `llama3.2`; `qwen2.5:1.5b` is fastest of all. The web HUD
streams replies as they're generated so it feels quicker; the voice assistant
speaks as soon as the first sentence is generated.

## Troubleshooting

- **"Ollama isn't running"** — start Ollama from your system tray.
- **"…since qwen2.5:1.5b is not installed"** — pull it: `ollama pull qwen2.5:1.5b`
- **Nothing heard** — Jarvis learns the room's noise level for the first
  half-second after speaking; speak after the greeting finishes.
- **Voice won't work** — the HUD's voice buttons need Chrome or Edge and
  microphone permission; `assistant.py` uses your default Windows mic.
- **Logs** — everything said and heard is in `assistant.log` (voice) and
  `jarvis_web.log` (HUD).
