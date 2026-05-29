"""
Gmail tools — read unread emails via Gmail API (read-only).

First-run setup:
  1. In Google Cloud Console, enable the Gmail API for your project.
  2. Your existing ~/.friday/google_credentials.json works — same OAuth app.
  3. Run: python -c "from friday.tools.gmail_tool import _get_service; _get_service(); print('Authorized.')"
     This opens a browser for one-time Gmail authorization (separate token from Calendar).
"""

import asyncio
import base64
import re
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".friday" / "google_credentials.json"
TOKEN_PATH       = Path.home() / ".friday" / "google_gmail_token.json"
SCOPES           = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_service():
    """Build and return an authenticated Gmail service (blocking)."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API dependencies missing. "
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

    return build("gmail", "v1", credentials=creds)


def _clean(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def register(mcp):

    @mcp.tool()
    async def get_unread_emails(max_results: int = 5) -> str:
        """
        Fetch and summarize the most recent unread emails from Gmail inbox.
        Use when asked about emails, inbox, messages, or mail.
        max_results: how many emails to retrieve (default 5, max 10)
        """
        if not CREDENTIALS_PATH.exists():
            return "Gmail not set up yet, boss. Place your credentials at ~/.friday/google_credentials.json."

        max_results = min(max_results, 10)

        try:
            service = await asyncio.get_event_loop().run_in_executor(None, _get_service)

            def _fetch():
                result = service.users().messages().list(
                    userId="me",
                    labelIds=["INBOX", "UNREAD"],
                    maxResults=max_results,
                ).execute()
                messages = result.get("messages", [])

                emails = []
                for msg in messages:
                    detail = service.users().messages().get(
                        userId="me",
                        id=msg["id"],
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    ).execute()

                    headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
                    subject = headers.get("Subject", "(no subject)")
                    sender  = headers.get("From", "Unknown")
                    snippet = _clean(detail.get("snippet", ""))[:150]

                    # Extract just the name or email from "Name <email>" format
                    sender_clean = re.sub(r"\s*<[^>]+>", "", sender).strip() or sender

                    emails.append(f"**From:** {sender_clean}\n**Subject:** {subject}\n{snippet}")

                return emails

            emails = await asyncio.get_event_loop().run_in_executor(None, _fetch)

            if not emails:
                return "Inbox is clear, boss. No unread messages."

            count = len(emails)
            header = f"## {count} unread email{'s' if count > 1 else ''}\n"
            return header + "\n\n---\n".join(emails)

        except Exception as e:
            return f"Gmail unavailable right now, boss: {e}"
