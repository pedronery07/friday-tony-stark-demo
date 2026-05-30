# F.R.I.D.A.Y. — Tony Stark AI Assistant

> *"Fully Responsive Intelligent Digital Assistant for You"*

A Tony Stark-inspired voice AI assistant built on [LiveKit Agents](https://github.com/livekit/agents) and [FastMCP](https://github.com/jlowin/fastmcp). Speak to it, it listens, reasons, and responds — with access to live news, weather, your calendar, Spotify, Gmail, GitHub activity, reminders, and persistent memory.

---

## Architecture

```
Microphone
    │
    ▼
STT  (Groq — whisper-large-v3-turbo)
    │
    ▼
LLM  (Gemini 2.0 Flash)  ◄──► MCP Server  (FastMCP / SSE · port 8000)
    │                              ├─ get_world_news / get_brazil_news / open_world_monitor
    ▼                              ├─ get_weather
TTS  (Deepgram — aura-2-thalia-en) ├─ get_today_schedule / get_week_schedule
    │                              ├─ create_calendar_event / delete_calendar_event
    ▼                              ├─ get_unread_emails
Speaker / LiveKit room             ├─ play_music / pause_music / ... (Spotify)
                                   ├─ get_github_activity
                                   ├─ set_reminder / list_reminders / cancel_reminder
                                   ├─ summarize_url / get_clipboard
                                   └─ remember / recall / forget

friday_reminders.py  (systemd user service)
    └─ polls ~/.friday/timers.json → notify-send → reminders_missed.json
```

The voice agent connects to the MCP server via SSE at `http://127.0.0.1:8000/sse`.

---

## Project Structure

```
friday-tony-stark-demo/
├── server.py                # MCP server entry point  (uv run friday)
├── agent_friday.py          # Voice agent entry point (uv run friday_voice)
├── friday_reminders.py      # Reminder daemon (systemd user service)
├── pyproject.toml
├── .env.example             # Copy → .env and fill in your keys
├── OPERATIONS.md            # Production setup and deployment guide
│
└── friday/                  # MCP server package
    ├── config.py
    ├── tools/
    │   ├── web.py           # News (world, Brazil), summarize_url, open_world_monitor
    │   ├── weather.py       # get_weather — OpenWeatherMap
    │   ├── github_tool.py   # get_github_activity — commits, PRs, issues
    │   ├── calendar_tool.py # get_today/week_schedule, create/delete_calendar_event
    │   ├── gmail_tool.py    # get_unread_emails — Gmail read-only
    │   ├── spotify_tool.py  # play_music, pause, resume, next, previous, volume, devices
    │   ├── timers.py        # set_reminder, list_reminders, cancel_reminder
    │   ├── memory.py        # remember / recall / forget — local JSON storage
    │   └── system.py        # get_current_time, get_clipboard
    ├── prompts/             # MCP prompt templates
    └── resources/           # MCP resources (friday://info)
```

---

## Quick Start

### Prerequisites

- Python ≥ 3.11
- [`uv`](https://github.com/astral-sh/uv) — `curl -Lsf https://astral.sh/uv/install.sh | sh`
- A [LiveKit Cloud](https://cloud.livekit.io) project (free tier works)
- `xclip` for clipboard support — `sudo apt install xclip`

### 1. Clone & install

```bash
git clone <your-repo-url>
cd friday-tony-stark-demo
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in your API keys — see Environment Variables below
```

### 3. Run — two terminals

```bash
# Terminal 1 — MCP server (start this first)
uv run friday

# Terminal 2 — Voice agent
uv run friday_voice
```

Then open [agents-playground.livekit.io](https://agents-playground.livekit.io), paste your LiveKit credentials, and connect.

---

## Environment Variables

| Variable | Required | Where to get it |
|---|---|---|
| `LIVEKIT_URL` | ✅ | [LiveKit Cloud](https://cloud.livekit.io) → your project URL |
| `LIVEKIT_API_KEY` | ✅ | LiveKit Cloud → API Keys |
| `LIVEKIT_API_SECRET` | ✅ | LiveKit Cloud → API Keys |
| `GROQ_API_KEY` | ✅ | [console.groq.com](https://console.groq.com) — STT |
| `GOOGLE_API_KEY` | ✅ | [aistudio.google.com](https://aistudio.google.com/projects) — LLM (Gemini 2.0 Flash) |
| `DEEPGRAM_API_KEY` | ✅ | [console.deepgram.com](https://console.deepgram.com) — TTS |
| `OPENWEATHERMAP_API_KEY` | optional | [openweathermap.org](https://openweathermap.org/api) — free tier |
| `WEATHER_CITY` | optional | Default city for weather queries (e.g. `São Paulo`) |
| `FRIDAY_TIMEZONE` | optional | IANA timezone override (auto-detected from `WEATHER_CITY` if blank) |
| `GITHUB_USERNAME` | optional | Your GitHub username — for activity feed |
| `GITHUB_TOKEN` | optional | GitHub personal access token — needed for private repos |
| `SPOTIFY_CLIENT_ID` | optional | [developer.spotify.com](https://developer.spotify.com) — requires Premium |
| `SPOTIFY_CLIENT_SECRET` | optional | Spotify Developer Dashboard |

**Google Calendar & Gmail** use OAuth2. Place credentials at `~/.friday/google_credentials.json` and run the one-time auth — see `OPERATIONS.md`.

---

## Switching Providers

Edit the constants at the top of `agent_friday.py`:

```python
STT_PROVIDER  = "groq"    # "groq" | "whisper"
LLM_PROVIDER  = "gemini"  # "gemini" | "groq" | "openai"
TTS_PROVIDER  = "deepgram"

GEMINI_LLM_MODEL = "gemini-2.0-flash"   # 1M TPM, 1500 req/day free tier
GROQ_LLM_MODEL   = "llama-3.3-70b-versatile"  # fallback; 12K TPM free tier
```

> **Note:** Groq's free tier (12K TPM) is too small for an agent with 20+ MCP tool schemas. Gemini 2.0 Flash is the recommended LLM for free-tier usage.

---

## Adding a New Tool

1. Create a file in `friday/tools/` with a `register(mcp)` function
2. Decorate each tool with `@mcp.tool()`
3. Import and call `register(mcp)` in `friday/tools/__init__.py`
4. Add the trigger phrases and behavior to the `SYSTEM_PROMPT` in `agent_friday.py`

The MCP server picks it up on next start.

---

## Tech Stack

- **[FastMCP](https://github.com/jlowin/fastmcp)** — MCP server framework
- **[LiveKit Agents](https://github.com/livekit/agents)** — real-time voice pipeline
- **Groq** (`whisper-large-v3-turbo`) — Speech-to-Text
- **Gemini** (`gemini-2.0-flash`) — LLM (default) · also supports Groq llama-3.3-70b / OpenAI GPT-4o
- **Deepgram** (`aura-2-thalia-en`) — Text-to-Speech
- **Silero VAD** — Voice Activity Detection
- **[uv](https://github.com/astral-sh/uv)** — Python package manager

---

## Credits

Forked from [SAGAR-TAMANG/friday-tony-stark-demo](https://github.com/SAGAR-TAMANG/friday-tony-stark-demo) — the original project that laid the foundation for this assistant.

---

## License

MIT
