"""
Google Calendar tools — read and write via OAuth2.

First-run setup:
  1. Go to Google Cloud Console → APIs & Services → Credentials
  2. Create an OAuth 2.0 Client ID (Desktop app)
  3. Download the JSON and save it to ~/.friday/google_credentials.json
  4. Run: python -c "from friday.tools.calendar_tool import _get_service; _get_service()"
  5. The token is stored at ~/.friday/google_token.json for all future runs

If you previously authorized with read-only scope, delete the old token first:
  rm ~/.friday/google_token.json
"""

import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta

CREDENTIALS_PATH = Path.home() / ".friday" / "google_credentials.json"
TOKEN_PATH = Path.home() / ".friday" / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


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

    @mcp.tool()
    async def get_week_schedule() -> str:
        """
        Retrieve all events from today through the end of the current week (Sunday).
        Use when asked about the week, upcoming events, or what's coming up.
        Trigger phrases: "What's on this week?" / "Any events this week?" / "What's coming up?"
        """
        if not CREDENTIALS_PATH.exists():
            return "Google Calendar not set up yet, boss."

        try:
            service = await asyncio.get_event_loop().run_in_executor(None, _get_service)

            now = datetime.now(timezone.utc)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # End of Sunday of the current week
            days_until_sunday = 6 - start.weekday() if start.weekday() != 6 else 0
            end = start + timedelta(days=days_until_sunday + 1)

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
                return "Nothing on the books for the rest of this week, boss."

            # Group events by day
            from collections import defaultdict
            by_day = defaultdict(list)
            for ev in events:
                start_raw = ev["start"].get("dateTime", ev["start"].get("date", ""))
                if "T" in start_raw:
                    dt = datetime.fromisoformat(start_raw)
                    day_key = dt.strftime("%A, %B %d")
                    time_str = dt.strftime("%H:%M")
                else:
                    dt = datetime.fromisoformat(start_raw)
                    day_key = dt.strftime("%A, %B %d")
                    time_str = "All day"
                title = ev.get("summary", "Untitled")
                location = ev.get("location", "")
                entry = f"  - {time_str}: {title}"
                if location:
                    entry += f"  ({location})"
                by_day[day_key].append(entry)

            lines = [f"## Week ahead — from {now.strftime('%A, %B %d')}\n"]
            for day, entries in by_day.items():
                lines.append(f"**{day}**")
                lines.extend(entries)
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            return f"Calendar unavailable right now, boss: {e}"

    @mcp.tool()
    async def create_calendar_event(
        title: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
    ) -> str:
        """
        Create a new event in Google Calendar.
        Use when asked to schedule, add, or create a calendar event or meeting.

        start and end must be ISO 8601 strings with timezone offset, e.g.:
          '2026-05-30T15:00:00-03:00'  (Brazil UTC-3)
        If the user says 'tomorrow at 3pm', convert to the correct ISO string.
        Default duration is 1 hour if end time is not specified.
        """
        if not CREDENTIALS_PATH.exists():
            return "Google Calendar not set up yet, boss."

        try:
            service = await asyncio.get_event_loop().run_in_executor(None, _get_service)

            event_body = {
                "summary": title,
                "start": {"dateTime": start, "timeZone": "America/Sao_Paulo"},
                "end": {"dateTime": end, "timeZone": "America/Sao_Paulo"},
            }
            if description:
                event_body["description"] = description
            if location:
                event_body["location"] = location

            def _create():
                return service.events().insert(calendarId="primary", body=event_body).execute()

            event = await asyncio.get_event_loop().run_in_executor(None, _create)

            start_dt = datetime.fromisoformat(start)
            return (
                f"Done. '{title}' is on the books for "
                f"{start_dt.strftime('%A, %B %d at %H:%M')}."
            )

        except Exception as e:
            return f"Couldn't create the event, boss: {e}"

    @mcp.tool()
    async def delete_calendar_event(title_keyword: str, date: str = "") -> str:
        """
        Delete a calendar event by searching for its title.
        Use when asked to remove, cancel, or delete a calendar event.

        title_keyword: part of the event title to search for
        date: optional date string to narrow the search (e.g. 'today', '2026-05-30')
        """
        if not CREDENTIALS_PATH.exists():
            return "Google Calendar not set up yet, boss."

        try:
            service = await asyncio.get_event_loop().run_in_executor(None, _get_service)

            now = datetime.now(timezone.utc)
            time_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
            time_max = time_min + timedelta(days=30)

            def _search():
                return (
                    service.events()
                    .list(
                        calendarId="primary",
                        timeMin=time_min.isoformat(),
                        timeMax=time_max.isoformat(),
                        q=title_keyword,
                        singleEvents=True,
                        orderBy="startTime",
                        maxResults=5,
                    )
                    .execute()
                )

            result = await asyncio.get_event_loop().run_in_executor(None, _search)
            events = result.get("items", [])

            if not events:
                return f"No upcoming events matching '{title_keyword}' found, boss."

            if len(events) > 1:
                titles = ", ".join(f"'{e.get('summary', 'Untitled')}'" for e in events)
                return f"Found multiple matches: {titles}. Be more specific so I know which one to delete."

            event = events[0]
            event_id = event["id"]
            event_title = event.get("summary", "Untitled")

            def _delete():
                service.events().delete(calendarId="primary", eventId=event_id).execute()

            await asyncio.get_event_loop().run_in_executor(None, _delete)
            return f"Done. '{event_title}' has been removed from your calendar."

        except Exception as e:
            return f"Couldn't delete the event, boss: {e}"
