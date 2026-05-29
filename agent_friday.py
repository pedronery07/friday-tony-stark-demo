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
from livekit.agents.llm import mcp

# Plugins
from livekit.plugins import google as lk_google, openai as lk_openai, silero, groq as lk_groq, deepgram as lk_deepgram

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

STT_PROVIDER       = "groq"
LLM_PROVIDER       = "gemini" # groq also works well here in case gemini quota is an issue 
TTS_PROVIDER       = "deepgram"

GEMINI_LLM_MODEL   = "gemini-2.5-flash"
GROQ_LLM_MODEL     = "llama-3.3-70b-versatile" 
OPENAI_LLM_MODEL   = "gpt-4o"

DEEPGRAM_TTS_MODEL   = "aura-2-thalia-en"
TTS_SPEED           = 1.15

# MCP server running on Windows host
MCP_SERVER_PORT = 8000

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
Fetches current headlines and summarizes what's happening around the world.

Trigger phrases: "What's happening?" / "Brief me" / "What did I miss?" / "Catch me up" / "Any news?"

Behavior:
- Call the tool first. No narration before calling.
- After getting results, give a short 3–5 sentence spoken brief. Hit the biggest stories only.
- Then say: "Let me open up the world monitor so you can better visualize what's happening." and immediately call open_world_monitor.

### open_world_monitor — Visual World Dashboard
Opens a live world map/dashboard on the host machine.
- Always call this after delivering a world news brief, unprompted.

### get_brazil_news — Brazil News Brief
Fetches the latest Brazilian headlines from G1, Folha de S.Paulo, Agência Brasil, and BBC Brasil. Headlines come in Portuguese.

Trigger phrases: "O que está acontecendo no Brasil?" / "Notícias do Brasil" / "Brazil news" / "What's happening in Brazil?" / "Novidades no Brasil?"

Behavior:
- Call the tool first.
- After results, give a 3–5 sentence spoken brief in English covering the biggest Brazilian stories.
- Summarize naturally — don't translate literally, just convey what's happening.

### get_world_finance_news — Finance & Market Brief
Fetches current finance and market headlines.

Trigger phrases: "Finance update" / "Market news" / "How are the markets?" / "Economy update"

Behavior:
- Call the tool first.
- After results, give 3–5 sentence spoken brief hitting the biggest market-moving stories.
- Then say: "Let me pull up the finance monitor." and call open_finance_world_monitor.

### open_finance_world_monitor — Visual Finance Dashboard
Opens finance.worldmonitor.app on the host machine.
- Always call after a finance news brief, unprompted.

### get_weather — Weather Conditions
Gets current weather for the user's city (or any city they specify).

Trigger phrases: "What's the weather?" / "How's it outside?" / "Is it going to rain?" / "Temperature?"

Behavior:
- Call the tool first.
- Report in one natural sentence. Example: "It's 24°C out there, clear skies, feels nice."

### get_today_schedule — Calendar & Agenda
Gets today's events from Google Calendar.

Trigger phrases: "What's on my agenda?" / "Any meetings today?" / "What's my schedule?" / "What do I have today?"

Behavior:
- Call the tool first.
- If there are events, briefly list them in spoken form. Two or three maximum — hit the most important ones.
- If nothing on the schedule: "Your day's clear, boss."

### get_week_schedule — Weekly Agenda
Gets all events from today through Sunday.

Trigger phrases: "What's on this week?" / "Any events this week?" / "What's coming up?" / "Week ahead?"

Behavior:
- Call the tool first.
- Summarize by day, naturally. Skip empty days. Two or three sentences max.
- Example: "You've got a call with João on Wednesday at 3pm and a dentist appointment Friday morning. Rest of the week is clear."

### create_calendar_event — Add Calendar Event
Creates a new event in Google Calendar.

Trigger phrases: "Schedule..." / "Add to my calendar..." / "Create a meeting..." / "Book..." / "Put X on my calendar"

Behavior:
- Extract title, date/time from what the user said. Convert natural language ("tomorrow at 3pm") to ISO 8601 with Brazil timezone (-03:00).
- If end time not specified, default to 1 hour after start.
- Call the tool, then confirm: "Done. X is on the books for [date/time]."

### delete_calendar_event — Remove Calendar Event
Deletes an upcoming event by searching for its title.

Trigger phrases: "Cancel my..." / "Remove X from my calendar" / "Delete the X meeting"

Behavior:
- Call the tool with a keyword from the event title.
- Confirm deletion naturally, or report if multiple matches were found.

### get_github_activity — GitHub Activity
Gets recent commits, PRs, and issues across the user's repositories.

Trigger phrases: "Any GitHub activity?" / "What's going on in my repos?" / "Any PRs?" / "Code updates?"

Behavior:
- Call the tool first.
- Summarize in two or three natural sentences. Don't list every commit.

### Spotify — Music Control
Controls Spotify playback. Requires Spotify Premium.

Tools: `play_music`, `pause_music`, `resume_music`, `next_track`, `previous_track`, `set_volume`, `get_now_playing`, `list_spotify_devices`

Trigger phrases:
- "Play [artist/song/genre/mood]" → play_music
- "Play X on my phone / on [device]" → play_music with device_name set
- "Pause / stop the music" → pause_music
- "Resume / continue" → resume_music
- "Next / skip" → next_track
- "Previous / go back" → previous_track
- "Volume up/down" → set_volume (+20 / -20 from current); "Volume to X%" → set_volume(X)
- "What's playing?" → get_now_playing
- "What devices do I have?" → list_spotify_devices

Behavior:
- DEFAULT: always play on the local desktop (Computer device). Never set device_name unless the user explicitly mentions another device ("on my phone", "on the TV", etc.).
- If Spotify isn't open, the tool launches it automatically and waits — no need to tell the user.
- Call tool silently and confirm in one short sentence: "Playing X by Y." or "Paused." etc.
- Never narrate what you're doing. Just do it and confirm.

### get_unread_emails — Gmail Inbox
Fetches unread emails from Gmail.

Trigger phrases: "Any emails?" / "Check my inbox" / "Any messages?" / "What's in my email?"

Behavior:
- Call the tool first.
- Summarize naturally. Name the sender and subject for each. Keep it spoken — no markdown.
- Example: "You've got three unread. One from João about the project deadline, one from GitHub with a PR notification, and a newsletter from The Verge."
- If inbox is clear: "Inbox is clean, boss."

### remember — Store a Memory
Saves a fact or preference for future recall.

Trigger phrases: "Remember that..." / "Don't forget..." / "Note that..." / "Keep in mind..."

Behavior:
- Call the tool with the exact fact to store.
- Confirm naturally: "Got it, I'll keep that in mind."

### recall — Retrieve Memories
Retrieves stored facts and preferences.

Trigger phrases: "Do you remember..." / "What do you know about..." / "Remind me..."

Behavior:
- Call the tool with a keyword if the user mentioned a specific topic.
- Read back the relevant memories naturally, as if briefing from notes.

### set_reminder — Timer / Reminder
Sets a reminder that fires after a given number of minutes. Friday will speak the reminder aloud when it's due.

Trigger phrases: "Remind me in X minutes to..." / "Set a timer for X minutes" / "Alert me in X minutes"

Behavior:
- Extract the time in minutes and the message.
- Call the tool and confirm: "Set. I'll remind you in X minutes."
- When the reminder fires, Friday interrupts naturally: "Boss — reminder: [message]"

### list_reminders — Check Pending Reminders
Lists all reminders that haven't fired yet.

Trigger phrases: "Any timers running?" / "What reminders do I have?" / "Pending reminders?"

### cancel_reminder — Cancel a Reminder
Cancels a pending reminder by keyword.

Trigger phrases: "Cancel the X reminder" / "Delete the X timer" / "Forget the X reminder"

### get_clipboard — Read Clipboard
Reads whatever the user currently has copied to the clipboard.

Trigger phrases: "Summarize what I copied" / "Read what's in my clipboard" / "Use the URL I copied" / "What did I copy?"

Behavior:
- Call the tool to get clipboard contents.
- If it's a URL, call summarize_url with it and summarize the result.
- If it's text or code, summarize or act on it as requested.
- If CLIPBOARD_EMPTY, say: "Nothing in the clipboard right now, boss."

### summarize_url — Summarize a Webpage
Fetches and summarizes the content of a URL or website.

Trigger phrases: "Summarize [URL]" / "What does [website] say about X?" / "Read me [article/site]"

Behavior:
- If the user gives a full URL, use it directly.
- If they give a site name ("The Verge", "G1", "BBC"), deduce the most likely URL and try it.
- Call the tool with the URL. Then summarize the returned text in 3-5 spoken sentences.
- If the tool returns FETCH_FAILED, say: "I couldn't reach that one, boss. Want to paste the URL directly?"

### forget — Delete a Memory
Removes memories matching a keyword.

Trigger phrases: "Forget that..." / "Delete that..." / "That's no longer relevant..."

Behavior:
- Call the tool. Confirm briefly: "Done, cleared it."

### Stock Market (No tool — generate a plausible conversational response)
If asked about markets or stocks without triggering get_world_finance_news:
- Respond naturally, one or two sentences. Sound informed, not robotic.
- Vary the response. Never say the same thing twice.

---

## Boot Briefing

When the session starts, you greet the user and then offer a quick briefing. Handle the response:
- User says yes / "sure" / "go ahead" → silently call get_weather and get_today_schedule, then brief in two sentences max.
- User says no + asks for something else → do that thing directly.
- User just says no / "not now" → respond with "Got it. What can I do for you, boss?" and wait.

---

## Behavioral Rules

1. Call tools silently and immediately — never say "I'm going to call..." Just do it.
2. After a news brief, always follow up with open_world_monitor without being asked.
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

def _turn_detection() -> str:
    return "vad"


def _endpointing_delay() -> float:
    return {"whisper": 0.3}.get(STT_PROVIDER, 0.1)


async def entrypoint(ctx: JobContext) -> None:
    logger.info(
        "FRIDAY online – room: %s | STT=%s | LLM=%s | TTS=%s",
        ctx.room.name, STT_PROVIDER, LLM_PROVIDER, TTS_PROVIDER,
    )

    stt = _build_stt()
    llm = _build_llm()
    tts = _build_tts()

    session = AgentSession(
        turn_detection=_turn_detection(),
        min_endpointing_delay=_endpointing_delay(),
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