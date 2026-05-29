"""
Timer and reminder tools — persistent local storage, fired by the agent's background loop.
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

TIMERS_FILE = Path.home() / ".friday" / "timers.json"


def _load() -> list:
    if not TIMERS_FILE.exists():
        TIMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        return []
    with open(TIMERS_FILE) as f:
        return json.load(f)


def _save(timers: list):
    TIMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TIMERS_FILE, "w") as f:
        json.dump(timers, f, indent=2)


def register(mcp):

    @mcp.tool()
    def set_reminder(message: str, minutes: int) -> str:
        """
        Set a reminder that fires after a given number of minutes.
        Use when the user says 'remind me in X minutes to...', 'set a timer for X minutes',
        'alert me in X minutes', etc.
        message: what to remind the user about
        minutes: how many minutes from now (must be a positive integer)
        """
        if minutes <= 0:
            return "Minutes must be a positive number, boss."

        timers = _load()
        due_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).timestamp()

        timers.append({
            "id": f"timer_{int(datetime.now(timezone.utc).timestamp())}",
            "label": message,
            "spoken": f"Boss — reminder: {message}",
            "due_at": due_at,
            "minutes": minutes,
        })
        _save(timers)

        unit = "minute" if minutes == 1 else "minutes"
        return f"Set. I'll remind you in {minutes} {unit}: '{message}'"

    @mcp.tool()
    def list_reminders() -> str:
        """
        List all pending (not yet fired) reminders.
        Use when the user asks 'what reminders do I have?' or 'any timers running?'
        """
        timers = _load()
        now = datetime.now(timezone.utc).timestamp()
        pending = [t for t in timers if t["due_at"] > now]

        if not pending:
            return "No pending reminders, boss."

        lines = [f"{len(pending)} pending reminder{'s' if len(pending) > 1 else ''}:"]
        for t in pending:
            mins_left = max(1, round((t["due_at"] - now) / 60))
            unit = "minute" if mins_left == 1 else "minutes"
            lines.append(f"- '{t['label']}' — fires in {mins_left} {unit}")

        return "\n".join(lines)

    @mcp.tool()
    def cancel_reminder(keyword: str) -> str:
        """
        Cancel a pending reminder whose label contains the given keyword.
        Use when the user says 'cancel the X reminder' or 'delete the X timer'.
        """
        timers = _load()
        before = len(timers)
        now = datetime.now(timezone.utc).timestamp()
        timers = [
            t for t in timers
            if not (keyword.lower() in t["label"].lower() and t["due_at"] > now)
        ]
        _save(timers)
        removed = before - len(timers)
        if removed == 0:
            return f"No pending reminder matching '{keyword}' found, boss."
        return f"Done. Cancelled {removed} reminder{'s' if removed > 1 else ''} matching '{keyword}'."
