# F.R.I.D.A.Y. — Operations Guide

## Talking to Friday

Open the LiveKit Agents Playground and connect to your project:

**→ https://agents-playground.livekit.io/**

Your project URL and credentials are in `.env` (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`).
Paste them in the playground settings, then hit **Connect**.

---

## Architecture

Two processes run permanently as systemd services:

```
Boot
 ├── friday-mcp.service    →  uv run friday          (MCP tools, port 8000)
 └── friday-agent.service  →  uv run agent_friday.py dev  (voice, LiveKit)
```

The agent depends on the MCP server — if MCP is down, the agent won't start.
Both services restart automatically on failure (`Restart=on-failure`).

External data stored in `~/.friday/` (outside the repo, never committed):
- `memory.json` — persistent memories
- `google_credentials.json` — Google Calendar OAuth credentials
- `google_token.json` — auto-generated after first Calendar auth

---

## Daily Use

Nothing to do — both services start automatically on boot.

Useful commands:

```bash
# Check service health
systemctl status friday-mcp friday-agent

# Live logs
journalctl -u friday-agent -f
journalctl -u friday-mcp -f

# Manual restart
sudo systemctl restart friday-mcp friday-agent

# Disable autostart
sudo systemctl disable friday-mcp friday-agent
```

---

## One-Time Setup (first install)

```bash
# 1. Install service files
sudo cp friday-mcp.service /etc/systemd/system/
sudo cp friday-agent.service /etc/systemd/system/
sudo systemctl daemon-reload

# 2. Enable and start
sudo systemctl enable friday-mcp friday-agent
sudo systemctl start friday-mcp friday-agent

# 3. Install dependencies (inside venv)
source .venv/bin/activate
uv sync
```

Service files are gitignored (`friday-*`) and stay local only.

---

## Development Workflow

When making changes and testing locally:

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

---

## Deploying Updates

After pushing changes to GitHub, deploy to the local production instance:

```bash
./deploy.sh
```

This script does:
1. `git pull` — fetches latest changes
2. `uv sync` — installs any new dependencies
3. `systemctl restart` — reloads both services

`deploy.sh` is gitignored (`*.sh`) and stays local only.

> **Note:** Updates are **not automatic**. You must run `./deploy.sh` manually after each push.

---

## Capabilities

| Trigger | What Friday does |
|---|---|
| "What's happening?" / "Any news?" | Global news brief → opens world monitor |
| "Notícias do Brasil" / "Brazil news" | Brazilian news brief (G1, Folha, BBC Brasil) |
| "Finance update" / "Markets?" | Finance brief → opens finance monitor |
| "What's the weather?" | Current conditions for your city |
| "What's on my agenda?" | Today's Google Calendar events |
| "Any GitHub activity?" | Recent commits, PRs, issues |
| "Remember that..." | Stores a fact to `~/.friday/memory.json` |
| "Do you remember..." | Recalls stored facts |
| "Forget that..." | Deletes matching memories |
