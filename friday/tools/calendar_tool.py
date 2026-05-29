"""
Google Calendar tools — read today's schedule via OAuth2.

First-run setup:
  1. Go to Google Cloud Console → APIs & Services → Credentials
  2. Create an OAuth 2.0 Client ID (Desktop app)
  3. Download the JSON and save it to ~/.friday/google_credentials.json
  4. Run the MCP server once — it will open a browser for you to authorize
  5. The token is stored at ~/.friday/google_token.json for all future runs
"""

import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta

CREDENTIALS_PATH = Path.home() / ".friday" / "google_credentials.json"
TOKEN_PATH = Path.home() / ".friday" / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_service():
    """Build and return an authenticated Google Calendar service (blocking)."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google Calendar dependencies missing. "
            "Run: uv add google-auth google-auth-oauthlib google-api-python-client"
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def register(mcp):

    @mcp.tool()
    async def get_today_schedule() -> str:
        """
        Retrieve today's events from Google Calendar.
        Use when asked about the schedule, agenda, meetings, or what's on today.
        """
        if not CREDENTIALS_PATH.exists():
            return (
                "Google Calendar not set up yet, boss. "
                "Place your credentials file at ~/.friday/google_credentials.json."
            )

        try:
            service = await asyncio.get_event_loop().run_in_executor(None, _get_service)

            now = datetime.now(timezone.utc)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)

            result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = result.get("items", [])

            if not events:
                return "Schedule's clear today, boss. Nothing on the books."

            lines = [f"## Schedule for {now.strftime('%A, %B %d')}\n"]
            for ev in events:
                start_raw = ev["start"].get("dateTime", ev["start"].get("date", ""))
                if "T" in start_raw:
                    dt = datetime.fromisoformat(start_raw)
                    time_str = dt.strftime("%H:%M")
                else:
                    time_str = "All day"
                title = ev.get("summary", "Untitled")
                location = ev.get("location", "")
                line = f"- {time_str}: {title}"
                if location:
                    line += f"  ({location})"
                lines.append(line)

            return "\n".join(lines)

        except Exception as e:
            return f"Calendar unavailable right now, boss: {e}"
