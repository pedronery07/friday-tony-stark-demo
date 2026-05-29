"""
System tools — time, environment info, clipboard, etc.
"""

import datetime
import platform
import subprocess


def register(mcp):

    @mcp.tool()
    def get_current_time() -> str:
        """Return the current date and time in ISO 8601 format."""
        return datetime.datetime.now().isoformat()

    @mcp.tool()
    def get_system_info() -> dict:
        """Return basic information about the host system."""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        }

    @mcp.tool()
    def get_clipboard() -> str:
        """
        Read the current contents of the system clipboard.
        Use when the user says 'summarize what I copied', 'read what's in my clipboard',
        'use the URL I copied', or any variation of acting on copied content.
        Works with URLs, text, code, or anything the user has copied.
        """
        # Try Wayland first (wl-paste), then X11 (xclip / xsel)
        candidates = [
            ["wl-paste", "--no-newline"],
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ]
        for cmd in candidates:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except FileNotFoundError:
                continue
            except Exception:
                continue

        return "CLIPBOARD_EMPTY: Nothing in the clipboard right now, boss."
