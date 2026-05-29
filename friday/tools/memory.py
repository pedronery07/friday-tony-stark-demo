"""
Memory tools — persistent local storage of facts across sessions.
"""

import json
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path.home() / ".friday" / "memory.json"


def _load() -> list:
    if not MEMORY_FILE.exists():
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        return []
    with open(MEMORY_FILE) as f:
        return json.load(f)


def _save(memories: list):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, "w") as f:
        json.dump(memories, f, indent=2, ensure_ascii=False)


def register(mcp):

    @mcp.tool()
    def remember(fact: str) -> str:
        """
        Store a fact, preference, or piece of information to remember for future sessions.
        Use when the user says 'remember that', 'don't forget', 'note that', etc.
        """
        memories = _load()
        entry = {"fact": fact, "timestamp": datetime.now().isoformat()}
        memories.append(entry)
        _save(memories)
        return f"Logged it. I'll remember: '{fact}'"

    @mcp.tool()
    def recall(topic: str = "") -> str:
        """
        Retrieve stored memories. Optionally pass a keyword to filter by topic.
        Use when the user asks 'do you remember', 'what do you know about', 'remind me', etc.
        """
        memories = _load()
        if not memories:
            return "Nothing stored yet, boss. You haven't asked me to remember anything."

        if topic:
            filtered = [m for m in memories if topic.lower() in m["fact"].lower()]
            if not filtered:
                return f"Nothing on record about '{topic}', boss."
        else:
            filtered = memories[-15:]

        lines = [f"- {m['fact']}  ({m['timestamp'][:10]})" for m in filtered]
        return "Here's what I have on file:\n" + "\n".join(lines)

    @mcp.tool()
    def forget(keyword: str) -> str:
        """
        Delete memories that contain a specific keyword.
        Use when the user says 'forget that', 'delete that', 'remove that from your memory', etc.
        """
        memories = _load()
        before = len(memories)
        memories = [m for m in memories if keyword.lower() not in m["fact"].lower()]
        _save(memories)
        removed = before - len(memories)
        if removed == 0:
            return f"Nothing matched '{keyword}' in my records, boss."
        return f"Done. Cleared {removed} entr{'y' if removed == 1 else 'ies'} matching '{keyword}'."
