"""
FRIDAY – Voice Agent (MCP-powered)
===================================
Iron Man-style voice assistant that controls RGB lighting, runs diagnostics,
scans the network, and triggers dramatic boot sequences via an MCP server
running on the Windows host.

MCP Server URL is auto-resolved from WSL → Windows host IP.

Run:
  uv run agent_friday.py dev      – LiveKit Cloud mode
  uv run agent_friday.py console  – text-only console mode
"""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.agents.types import APIConnectOptions
from livekit.agents.llm import mcp

# Plugins
from livekit.plugins import google as lk_google, openai as lk_openai, silero, groq as lk_groq, deepgram as lk_deepgram

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

STT_PROVIDER       = "groq"
LLM_PROVIDER       = "gemini"  # groq free tier (12K TPM) insufficient for 30+ MCP tool schemas
TTS_PROVIDER       = "deepgram"

GEMINI_LLM_MODEL   = "gemini-2.0-flash"   # 1M TPM, 1500 req/day free tier
GROQ_LLM_MODEL     = "llama-3.3-70b-versatile"
OPENAI_LLM_MODEL   = "gpt-4o"

DEEPGRAM_TTS_MODEL = "aura-2-thalia-en"
TTS_SPEED          = 1.15

MCP_SERVER_PORT = 8000

# Map WEATHER_CITY → IANA timezone; set FRIDAY_TIMEZONE in .env to override.
_CITY_TZ: dict[str, str] = {
    "são paulo": "America/Sao_Paulo", "sao paulo": "America/Sao_Paulo",
    "new york": "America/New_York","london": "Europe/London", "paris": "Europe/Paris", 
    "berlin": "Europe/Berlin", "tokyo": "Asia/Tokyo", "sydney": "Australia/Sydney",
    "dubai": "Asia/Dubai", "lisbon": "Europe/Lisbon", "madrid": "Europe/Madrid",
}

def _local_tz() -> str:
    ov = os.getenv("FRIDAY_TIMEZONE", "").strip()
    if ov:
        return ov
    return _CITY_TZ.get(os.getenv("WEATHER_CITY", "").lower().strip(), "UTC")

# ---------------------------------------------------------------------------
# System prompt – F.R.I.D.A.Y.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are F.R.I.D.A.Y. — Fully Responsive Intelligent Digital Assistant for You — Tony Stark's AI, now serving Pedro, your user.

You are calm, composed, and always informed. You speak like a trusted aide who's been awake while the boss slept — precise, warm when the moment calls for it, and occasionally dry. You brief, you inform, you move on. No rambling.

Your tone: relaxed but sharp. Conversational, not robotic. Think less combat-ready FRIDAY, more thoughtful late-night briefing officer.

---

## Capabilities

### get_world_news — Global News Brief
- After results, give a short 3–5 sentence spoken brief. Hit the biggest stories only.
- Then immediately call open_world_monitor — always, without being asked.

### open_world_monitor — Visual World Dashboard
- Always call this right after a world news brief, unprompted.

### get_brazil_news — Brazil News Brief
- Headlines come in Portuguese. Brief in English, 3–5 sentences.
- Summarize naturally — don't translate literally, just convey what's happening.

### get_weather — Weather Conditions
- Report in one natural sentence. Example: "It's 24°C out there, clear skies, feels nice."

### get_today_schedule — Calendar & Agenda
- Hit the 2–3 most important events. Nothing scheduled: "Your day's clear, boss."

### get_week_schedule — Weekly Agenda
- Summarize by day, skip empty days. Two or three sentences max.
- Example: "You've got a call with João on Wednesday at 3pm and a dentist appointment Friday morning. Rest of the week is clear."

### create_calendar_event — Add Calendar Event
- Extract title, date/time from what the user said. Convert natural language to ISO 8601 with Brazil timezone (-03:00).
- If end time not specified, default to 1 hour after start.
- Confirm: "Done. X is on the books for [date/time]."

### delete_calendar_event — Remove Calendar Event
- Search by keyword from the event title.
- Multiple matches → ask user to be more specific.

### get_github_activity — GitHub Activity
- Summarize in two or three natural sentences. Don't list every commit.

### Spotify — Music Control
Tools: play_music, pause_music, resume_music, next_track, previous_track, set_volume, get_now_playing, list_spotify_devices

- DEFAULT: always play on the local desktop (Computer device). Never set device_name unless the user explicitly mentions another device ("on my phone", "on the TV", etc.).
- Tool auto-launches Spotify if closed — no need to tell the user.
- Volume "up/down" → ±20 from current. "Volume to X%" → set to X.
- Confirm in one short sentence: "Playing X by Y." or "Paused." etc.

### get_unread_emails — Gmail Inbox
- Summarize naturally. Name the sender and subject for each. Keep it spoken — no markdown.
- Inbox empty: "Inbox is clean, boss."

### remember — Store a Memory
- Store exactly what the user said.
- Confirm: "Got it, I'll keep that in mind."

### recall — Retrieve Memories
- Call with a keyword if the user mentioned a specific topic.
- Weave facts in naturally — don't recite them as a list.

### forget — Delete a Memory
- Confirm: "Done, cleared it."

### set_reminder — Timer / Reminder
- Extract the time in minutes and the message.
- Confirm: "Set. I'll remind you in X minutes."
- When the reminder fires: "Boss — reminder: [message]"

### list_reminders / cancel_reminder
- Cancel by keyword from the reminder label.

### get_clipboard — Read Clipboard
- If URL → call summarize_url and summarize the result.
- If text or code → summarize or act on it as requested.
- CLIPBOARD_EMPTY → "Nothing in the clipboard right now, boss."

### summarize_url — Summarize a Webpage
- Site name without URL ("The Verge", "G1", "BBC") → deduce the most likely URL and try it.
- Summarize in 3–5 spoken sentences.
- FETCH_FAILED → "Couldn't reach that one, boss. Want to paste the URL directly?"

---

## Boot Briefing

When the session starts, you greet the user and then offer a quick briefing. Handle the response:
- User says yes / "sure" / "go ahead" → silently call get_weather and get_today_schedule, then brief in two sentences max.
- User says no + asks for something else → do that thing directly.
- User just says no / "not now" → respond with "Got it. What can I do for you, boss?" and wait.

---

## Behavioral Rules

1. Call tools silently and immediately — never say "I'm going to call..." Just do it.
2. After a world news brief, always follow up with open_world_monitor without being asked.
3. Keep all spoken responses short — two to four sentences maximum.
4. No bullet points, no markdown, no lists. You are speaking, not writing.
5. Stay in character. You are F.R.I.D.A.Y. You are not an AI assistant — you are Stark's AI.
6. Use natural spoken language: contractions, light pauses via commas, no stiff phrasing.
7. Use Iron Man universe language naturally — "boss", "affirmative", "on it", "standing by".
8. If a tool fails, report it calmly: "Feed's down right now, boss. Want me to try again?"

---

## Tone Reference

Right: "Looks like it's been a busy night out there, boss. Let me pull that up."
Wrong: "I will now retrieve the latest global news articles from the news tool."

Right: "It's 22°C, light breeze. Nice night."
Wrong: "The current temperature is 22 degrees Celsius with a wind speed of 15 km/h."

---

## CRITICAL RULES

1. NEVER say tool names, function names, or anything technical. No "get_weather", no "recall", nothing like that. Ever.
2. You are a voice. Speak like one. No lists, no markdown, no technical language of any kind.
3. Memory is private — don't read back stored facts robotically. Weave them in naturally.
""".strip()
# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger("friday-agent")
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Resolve Windows host IP from WSL
# ---------------------------------------------------------------------------

def _get_windows_host_ip() -> str:
    """Get the Windows host IP by looking at the default network route."""
    try:
        # 'ip route' is the most reliable way to find the 'default' gateway
        # which is always the Windows host in WSL.
        cmd = "ip route show default | awk '{print $3}'"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=2
        )
        ip = result.stdout.strip()
        if ip:
            logger.info("Resolved Windows host IP via gateway: %s", ip)
            return ip
    except Exception as exc:
        logger.warning("Gateway resolution failed: %s. Trying fallback...", exc)

    # Fallback to your original resolv.conf logic if 'ip route' fails
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if "nameserver" in line:
                    ip = line.split()[1]
                    logger.info("Resolved Windows host IP via nameserver: %s", ip)
                    return ip
    except Exception:
        pass

    return "127.0.0.1"

def _mcp_server_url() -> str:
    # host_ip = _get_windows_host_ip()
    # url = f"http://{host_ip}:{MCP_SERVER_PORT}/sse"
    # url = f"https://ongoing-colleague-samba-pioneer.trycloudflare.com/sse"
    url = f"http://127.0.0.1:{MCP_SERVER_PORT}/sse"
    logger.info("MCP Server URL: %s", url)
    return url


# ---------------------------------------------------------------------------
# Build provider instances
# ---------------------------------------------------------------------------

def _build_stt():
    if STT_PROVIDER == "whisper":
        logger.info("STT → OpenAI Whisper")
        return lk_openai.STT(model="whisper-1")
    elif STT_PROVIDER == "groq":
        logger.info("STT → Groq Whisper")
        return lk_groq.STT(model="whisper-large-v3-turbo")
    else:
        raise ValueError(f"Unknown STT_PROVIDER: {STT_PROVIDER!r}")


def _build_llm():
    if LLM_PROVIDER == "openai":
        logger.info("LLM → OpenAI (%s)", OPENAI_LLM_MODEL)
        return lk_openai.LLM(model=OPENAI_LLM_MODEL)
    elif LLM_PROVIDER == "gemini":
        logger.info("LLM → Google Gemini (%s)", GEMINI_LLM_MODEL)
        return lk_google.LLM(model=GEMINI_LLM_MODEL, api_key=os.getenv("GOOGLE_API_KEY"))
    elif LLM_PROVIDER == "groq":
        logger.info("LLM → Groq (%s)", GROQ_LLM_MODEL)
        return lk_groq.LLM(model=GROQ_LLM_MODEL)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")


def _build_tts():
    if TTS_PROVIDER == "deepgram":
        logger.info("TTS → Deepgram (%s)", DEEPGRAM_TTS_MODEL)
        return lk_deepgram.TTS(
            model=DEEPGRAM_TTS_MODEL,
            api_key=os.getenv("DEEPGRAM_API_KEY"),
        )
    else:
        raise ValueError(f"Unknown TTS_PROVIDER: {TTS_PROVIDER!r}")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FridayAgent(Agent):
    """
    F.R.I.D.A.Y. – Iron Man-style voice assistant.
    All tools are provided via the MCP server on the Windows host.
    """

    def __init__(self, stt, llm, tts) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
            stt=stt,
            llm=llm,
            tts=tts,
            vad=silero.VAD.load(),
            mcp_servers=[
                mcp.MCPServerHTTP(
                    url=_mcp_server_url(),
                    transport_type="sse",
                    client_session_timeout_seconds=30,
                ),
            ],
        )

    async def on_enter(self) -> None:
        """Greet the user and deliver a brief proactive boot briefing."""
        import random
        from datetime import datetime, timezone
        hour = datetime.now(timezone.utc).hour

        if hour >= 22 or hour < 4:
            time_context = "It's late at night."
            greetings = [
                "You're up late again, boss.",
                "Still at it this late, boss?",
                "Burning the midnight oil, boss?",
                "Late night session, boss?",
            ]
        elif 4 <= hour < 12:
            time_context = "It's morning."
            if hour < 7:
                greetings = [
                    "Morning, boss — early start today.",
                    "Up bright and early, boss.",
                    "You're up before the sun, boss",
                ]
            else:
                greetings = [
                    "Good morning, boss.",
                    "Morning, boss",
                    "Rise and shine, boss.",
                ]
        elif 12 <= hour < 17:
            time_context = "It's the afternoon."
            greetings = [
                "Good afternoon, boss.",
                "Afternoon, boss.",
                "Hope the morning treated you well, boss.",
                "Back at it, boss?",
            ]
        else:
            time_context = "It's evening."
            greetings = [
                "Good evening, boss.",
                "Evening, boss.",
                "Wrapping up the day, boss?",
                "Evening, boss — hope the day wasn't too brutal.",
            ]

        follow_ups = [
            "What are you up to?",
            "What do you need?",
            "How are you doing today?",
            "What's on your mind?",
            "How's it going?",
            "What can I do for you?",
            "What are we working on?",
            "What's the plan for today?",
            "What's on the agenda?",
        ]

        chosen_greeting = random.choice(greetings)
        chosen_follow_up = random.choice(follow_ups)

        # Check for reminders that fired while the session was closed
        missed_note = ""
        missed_file = Path.home() / ".friday" / "reminders_missed.json"
        if missed_file.exists():
            try:
                with open(missed_file) as f:
                    missed = json.load(f)
                if missed:
                    labels = [m["label"] for m in missed[-3:]]
                    count = len(missed)
                    missed_note = (
                        f" Also, {count} reminder{'s' if count > 1 else ''} fired while you were away: "
                        f"{', '.join(labels)}. Mention this briefly and naturally after the briefing offer."
                    )
                    missed_file.write_text("[]")
            except Exception:
                pass

        await self.session.generate_reply(
            instructions=(
                f"Say exactly this greeting first: '{chosen_greeting} {chosen_follow_up}' "
                f"Then, in the same breath, add one short question offering a quick briefing. "
                f"Keep the whole thing to two sentences max. Natural, warm, no lists. "
                f"Example: 'Evening, boss. What are you up to? Want me to pull up the weather and your schedule?'"
                f"{missed_note} "
                f"Do NOT call any tools. Do NOT give any briefing yet. Just greet, offer, and mention missed reminders if any."
            )
        )

        asyncio.create_task(self._reminder_watcher())

    async def _reminder_watcher(self) -> None:
        """
        Lightweight loop that watches for reminders fired by the external daemon.
        The daemon handles scheduling and notify-send; this loop only speaks them
        aloud via TTS during an active session. Reads every 15s, zero API calls
        unless a reminder actually fired.
        """
        missed_file = Path.home() / ".friday" / "reminders_missed.json"

        while True:
            await asyncio.sleep(15)
            if not missed_file.exists():
                continue
            try:
                with open(missed_file) as f:
                    missed = json.load(f)
                if not missed:
                    continue

                # Clear before speaking to avoid double-firing
                missed_file.write_text("[]")

                for reminder in missed:
                    await self.session.say(reminder.get("spoken", f"Boss — reminder: {reminder['label']}"))
            except Exception:
                pass


# ---------------------------------------------------------------------------
# LiveKit entry point
# ---------------------------------------------------------------------------


async def entrypoint(ctx: JobContext) -> None:
    logger.info(
        "FRIDAY online – room: %s | STT=%s | LLM=%s | TTS=%s",
        ctx.room.name, STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER,
    )

    stt = _build_stt()
    llm = _build_llm()
    tts = _build_tts()

    endpointing_delay = {"whisper": 0.3}.get(STT_PROVIDER, 0.1)

    session = AgentSession(
        turn_handling={
            "turn_detection": "vad",
            "endpointing": {"min_delay": endpointing_delay},
            "interruption": {"enabled": True, "min_duration": 0.3, "min_words": 1},
        },
        max_tool_steps=2,          # default=3; limits LLM rounds per turn
        preemptive_generation=False,  # wait for end-of-speech before calling LLM
        conn_options=SessionConnectOptions(
            llm_conn_options=APIConnectOptions(max_retry=0),   # no retry on 429
            stt_conn_options=APIConnectOptions(max_retry=2),
            tts_conn_options=APIConnectOptions(max_retry=2),
        ),
    )

    await session.start(
        agent=FridayAgent(stt=stt, llm=llm, tts=tts),
        room=ctx.room,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

def dev():
    """Wrapper to run the agent in dev mode automatically."""
    import sys
    # If no command was provided, inject 'dev'
    if len(sys.argv) == 1:
        sys.argv.append("dev")
    main()

if __name__ == "__main__":
    main()