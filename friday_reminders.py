"""
friday_reminders.py — Standalone reminder daemon.

Polls ~/.friday/timers.json every 15 seconds and fires desktop notifications
when timers are due. Runs as a systemd user service, completely independent
of the LiveKit voice session.

Fired reminders are logged to ~/.friday/reminders_missed.json so Friday can
mention them at the start of the next voice session.
"""

import json
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

TIMERS_FILE  = Path.home() / ".friday" / "timers.json"
MISSED_FILE  = Path.home() / ".friday" / "reminders_missed.json"
POLL_INTERVAL = 15  # seconds


def _load(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def _save(path: Path, data: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _notify(message: str):
    try:
        subprocess.run(
            ["notify-send", "F.R.I.D.A.Y.", message,
             "--icon=dialog-information", "--urgency=normal", "--expire-time=10000"],
            timeout=5,
        )
    except FileNotFoundError:
        # notify-send not installed — skip silently
        pass
    except Exception:
        pass


def main():
    print(f"Reminder daemon started. Polling every {POLL_INTERVAL}s.")

    while True:
        time.sleep(POLL_INTERVAL)

        timers = _load(TIMERS_FILE)
        if not timers:
            continue

        now = datetime.now(timezone.utc).timestamp()
        due       = [t for t in timers if t["due_at"] <= now]
        remaining = [t for t in timers if t["due_at"] > now]

        if not due:
            continue

        for timer in due:
            label = timer.get("label", "reminder")
            _notify(f"Reminder: {label}")
            print(f"Fired: {label}")

        # Log for Friday to mention at next session
        missed = _load(MISSED_FILE)
        missed.extend(due)
        _save(MISSED_FILE, missed)

        _save(TIMERS_FILE, remaining)


if __name__ == "__main__":
    main()
