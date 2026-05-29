# F.R.I.D.A.Y. — Operations Guide

## Talking to Friday

Open the LiveKit Agents Playground and connect to your project:

**→ https://agents-playground.livekit.io/**

Your project URL and credentials are in `.env` (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`).
Paste them in the playground settings, then hit **Connect**.

---

## Architecture

Three processes run permanently:

```
Boot
 ├── friday-mcp.service       →  uv run friday                (MCP tools, port 8000)  [system]
 ├── friday-agent.service     →  uv run agent_friday.py dev   (voice, LiveKit)        [system]
 └── friday-reminders.service →  uv run python friday_reminders.py  (reminder daemon) [user]
```

- MCP and agent are **system-level** services (`sudo systemctl`).
- Reminder daemon is a **user-level** service (`systemctl --user`) — needs access to the desktop for `notify-send`.
- All three restart automatically on failure.

External data stored in `~/.friday/` (outside the repo, never committed):

| File | Contents |
|---|---|
| `memory.json` | Persistent memories |
| `timers.json` | Pending reminders |
| `reminders_missed.json` | Reminders that fired while no session was active |
| `google_credentials.json` | Google Calendar OAuth credentials |
| `google_token.json` | Auto-generated after first Calendar auth |

---

## Daily Use

Nothing to do — all three services start automatically on boot.

```bash
# Check service health
systemctl status friday-mcp friday-agent
systemctl --user status friday-reminders

# Live logs
journalctl -u friday-agent -f
journalctl -u friday-mcp -f
journalctl --user -u friday-reminders -f

# Manual restart
sudo systemctl restart friday-mcp friday-agent
systemctl --user restart friday-reminders

# Disable autostart
sudo systemctl disable friday-mcp friday-agent
systemctl --user disable friday-reminders
```

---

## One-Time Setup (first install)

```bash
# 1. Install system service files (MCP + agent)
sudo cp friday-mcp.service /etc/systemd/system/
sudo cp friday-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable friday-mcp friday-agent
sudo systemctl start friday-mcp friday-agent

# 2. Install user service file (reminder daemon)
mkdir -p ~/.config/systemd/user/
cp friday-reminders.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable friday-reminders
systemctl --user start friday-reminders

# 3. Install dependencies (inside venv)
source .venv/bin/activate
uv sync

# 4. Install xclip (clipboard support)
sudo apt install xclip
```

Service files are gitignored (`friday-*`) and stay local only.

---

## Google Calendar Setup

Calendar uses OAuth2. Run this once to authorize — it opens a browser:

```bash
source .venv/bin/activate
python -c "from friday.tools.calendar_tool import _get_service; _get_service(); print('Authorized.')"
```

The token is saved to `~/.friday/google_token.json` and used automatically on all future runs.

> **If the token stops working** (scope changed or expired): delete it and re-run the command above.
> ```bash
> rm ~/.friday/google_token.json
> ```

---

## Development Workflow

```bash
# 1. Stop production services
sudo systemctl stop friday-mcp friday-agent

# 2. Run both processes manually (two terminals)
uv run friday                   # terminal 1 — MCP server
uv run agent_friday.py dev      # terminal 2 — voice agent

# 3. Make changes, test, iterate

# 4. Restore production services when done
sudo systemctl start friday-mcp friday-agent
```

The reminder daemon can stay running during development — it's independent.

---

## Deploying Updates

After pushing changes to GitHub:

```bash
./deploy.sh
```

This script: `git pull` → `uv sync` → `systemctl restart` (MCP + agent).

> **Updates are not automatic.** Run `./deploy.sh` manually after each push.
> The reminder daemon is not restarted by `deploy.sh` — restart it manually if `friday_reminders.py` changed:
> ```bash
> systemctl --user restart friday-reminders
> ```

---

## Capabilities

| Trigger | What Friday does |
|---|---|
| "What's happening?" / "Any news?" | Global news brief → opens world monitor |
| "Notícias do Brasil" / "Brazil news" | Brazilian news brief (G1, Folha, Agência Brasil, BBC Brasil) |
| "Finance update" / "Markets?" | Finance brief → opens finance monitor |
| "What's the weather?" | Current conditions for your city |
| "What's on my agenda?" | Today's Google Calendar events |
| "What's on this week?" | Events from today through Sunday, grouped by day |
| "Schedule a meeting tomorrow at 3pm" | Creates a Google Calendar event |
| "Cancel my X appointment" | Deletes a calendar event by title |
| "Remind me in 20 minutes to..." | Sets a reminder → desktop notification + spoken alert |
| "Any timers running?" | Lists pending reminders |
| "Cancel the X reminder" | Cancels a pending reminder |
| "Summarize what I copied" | Reads clipboard → fetches URL → summarizes |
| "Summarize bbc.com" | Fetches and summarizes a webpage |
| "Any GitHub activity?" | Recent commits, PRs, issues |
| "Remember that..." | Stores a fact to `~/.friday/memory.json` |
| "Do you remember..." | Recalls stored facts |
| "Forget that..." | Deletes matching memories |
