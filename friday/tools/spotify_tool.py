"""
Spotify tools — playback control via Spotify Web API (requires Premium).

Default device is always the local desktop (Computer type). Specify another
device explicitly if needed ("play on my phone").

First-run setup:
  1. Go to developer.spotify.com → Dashboard → Create app
  2. Set redirect URI to: http://127.0.0.1:8888/callback
  3. Copy Client ID and Client Secret to .env
  4. Run: python -c "from dotenv import load_dotenv; load_dotenv(); from friday.tools.spotify_tool import _get_sp; _get_sp(); print('Authorized.')"
     This opens a browser for one-time authorization.
"""

import os
import subprocess
import time
from pathlib import Path

CACHE_PATH = str(Path.home() / ".friday" / "spotify_cache")
SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
])

# Commands to try when launching Spotify on Linux (deb, snap, flatpak)
_SPOTIFY_LAUNCH_CMDS = [
    ["spotify"],
    ["snap", "run", "spotify"],
    ["flatpak", "run", "com.spotify.Client"],
]


def _get_sp():
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
    except ImportError:
        raise RuntimeError("spotipy not installed. Run: uv add spotipy")

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env")

    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope=SCOPES,
            cache_path=CACHE_PATH,
            open_browser=True,
        )
    )


def _launch_spotify():
    """Try to open the Spotify desktop app."""
    for cmd in _SPOTIFY_LAUNCH_CMDS:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            continue
    return False


def _get_desktop_device(sp, device_name: str = None) -> str | None:
    """
    Return the device_id of the local desktop (Computer type).
    If device_name is given, match by name instead (for explicit device selection).
    Returns None if not found.
    """
    try:
        devices = sp.devices().get("devices", [])
        if device_name:
            for d in devices:
                if device_name.lower() in d["name"].lower():
                    return d["id"]
        else:
            for d in devices:
                if d["type"] == "Computer":
                    return d["id"]
    except Exception:
        pass
    return None


def _ensure_desktop(sp) -> str | None:
    """
    Return the desktop device_id, launching Spotify if necessary.
    Waits up to 6s for the app to register with the API after launch.
    """
    device_id = _get_desktop_device(sp)
    if device_id:
        return device_id

    # No desktop device — try launching the app
    launched = _launch_spotify()
    if not launched:
        return None

    # Poll until device appears (max 6s)
    for _ in range(4):
        time.sleep(1.5)
        device_id = _get_desktop_device(sp)
        if device_id:
            return device_id

    return None


def register(mcp):

    @mcp.tool()
    def get_now_playing() -> str:
        """
        Get the currently playing track on Spotify.
        Use when asked 'What's playing?', 'What song is this?', 'What's on?'
        """
        try:
            sp = _get_sp()
            current = sp.current_playback()
            if not current or not current.get("item"):
                return "Nothing playing on Spotify right now, boss."

            track = current["item"]
            name = track["name"]
            artists = ", ".join(a["name"] for a in track["artists"])
            is_playing = current["is_playing"]
            progress_ms = current.get("progress_ms", 0)
            duration_ms = track["duration_ms"]
            progress = f"{progress_ms // 60000}:{(progress_ms % 60000) // 1000:02d}"
            duration = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
            status = "playing" if is_playing else "paused"

            return f"{name} by {artists} — {status} ({progress} / {duration})"

        except Exception as e:
            return f"Spotify unavailable, boss: {e}"

    @mcp.tool()
    def play_music(query: str, device_name: str = "") -> str:
        """
        Search for and play music on Spotify on the local desktop.
        Handles tracks, artists, albums, and playlists.
        Use when asked to play a song, artist, genre, playlist, or mood.
        query: natural language search, e.g. 'Tame Impala', 'lofi hip hop', 'Bohemian Rhapsody'
        device_name: optional — only set if the user explicitly asks to play on a specific device
                     (e.g. 'my phone', 'living room'). Leave empty to default to desktop.
        """
        try:
            sp = _get_sp()

            # Resolve target device
            if device_name:
                target_id = _get_desktop_device(sp, device_name)
                if not target_id:
                    return f"Couldn't find a device named '{device_name}', boss. Is it online?"
            else:
                target_id = _ensure_desktop(sp)
                if not target_id:
                    return (
                        "Couldn't find or launch Spotify on this machine, boss. "
                        "Try opening it manually first."
                    )

            # Determine search type from query keywords
            if any(w in query.lower() for w in ["playlist", "mix", "radio"]):
                search_type = "playlist"
            elif "album" in query.lower():
                search_type = "album"
            else:
                search_type = "track"

            results = sp.search(q=query, type=search_type, limit=1)
            items = results.get(f"{search_type}s", {}).get("items", [])

            if not items:
                results = sp.search(q=query, type="track", limit=1)
                items = results.get("tracks", {}).get("items", [])
                search_type = "track"

            if not items:
                return f"Couldn't find anything matching '{query}' on Spotify, boss."

            item = items[0]
            uri = item["uri"]

            if search_type == "track":
                sp.start_playback(device_id=target_id, uris=[uri])
                artists = ", ".join(a["name"] for a in item["artists"])
                return f"Playing '{item['name']}' by {artists}."
            else:
                sp.start_playback(device_id=target_id, context_uri=uri)
                return f"Playing {search_type} '{item['name']}'."

        except Exception as e:
            return f"Couldn't start playback, boss: {e}"

    @mcp.tool()
    def pause_music() -> str:
        """
        Pause Spotify playback.
        Use when asked to pause, stop, or mute the music.
        """
        try:
            sp = _get_sp()
            sp.pause_playback()
            return "Paused."
        except Exception as e:
            if "Restriction violated" in str(e):
                return "Already paused, boss."
            return f"Couldn't pause, boss: {e}"

    @mcp.tool()
    def resume_music() -> str:
        """
        Resume Spotify playback.
        Use when asked to resume, continue, or unpause the music.
        """
        try:
            sp = _get_sp()
            sp.start_playback()
            return "Resumed."
        except Exception as e:
            return f"Couldn't resume, boss: {e}"

    @mcp.tool()
    def next_track() -> str:
        """
        Skip to the next track on Spotify.
        Use when asked to skip, next song, or next track.
        """
        try:
            sp = _get_sp()
            sp.next_track()
            return "Skipped."
        except Exception as e:
            return f"Couldn't skip, boss: {e}"

    @mcp.tool()
    def previous_track() -> str:
        """
        Go back to the previous track on Spotify.
        Use when asked to go back, previous song, or replay.
        """
        try:
            sp = _get_sp()
            sp.previous_track()
            return "Going back."
        except Exception as e:
            return f"Couldn't go back, boss: {e}"

    @mcp.tool()
    def set_volume(level: int) -> str:
        """
        Set Spotify volume (0–100).
        Use when asked to change, raise, lower, or set the volume.
        level: integer between 0 and 100
        """
        level = max(0, min(100, level))
        try:
            sp = _get_sp()
            sp.volume(level)
            return f"Volume set to {level}%."
        except Exception as e:
            return f"Couldn't set volume, boss: {e}"

    @mcp.tool()
    def list_spotify_devices() -> str:
        """
        List all available Spotify devices on the account.
        Use when the user asks what devices are available or wants to switch device.
        """
        try:
            sp = _get_sp()
            devices = sp.devices().get("devices", [])
            if not devices:
                return "No Spotify devices found, boss."
            lines = ["Available Spotify devices:"]
            for d in devices:
                active = " (active)" if d["is_active"] else ""
                lines.append(f"- {d['name']} [{d['type']}]{active}")
            return "\n".join(lines)
        except Exception as e:
            return f"Couldn't list devices, boss: {e}"
