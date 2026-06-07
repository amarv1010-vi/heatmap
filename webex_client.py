"""
Thin Webex Messages API client. Just the calls the bot needs:
identify itself, read an incoming message, and post replies (chunked to the
Webex per-message size limit).
"""

import os
import time

import requests

WEBEX_API = "https://webexapis.com/v1"

# Webex rejects messages whose markdown exceeds ~7439 bytes. Stay safely under.
MAX_MESSAGE_CHARS = 7000


def _token() -> str:
    token = os.environ.get("WEBEX_BOT_TOKEN")
    if not token:
        raise RuntimeError("WEBEX_BOT_TOKEN is not set")
    return token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def get_me() -> dict:
    """The bot's own identity. Used to ignore the bot's own messages."""
    r = requests.get(f"{WEBEX_API}/people/me", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def get_message(message_id: str) -> dict:
    """Full message detail, including plain `text` and `roomId`."""
    r = requests.get(
        f"{WEBEX_API}/messages/{message_id}", headers=_headers(), timeout=15
    )
    r.raise_for_status()
    return r.json()


def _post_message(room_id: str, markdown: str) -> dict:
    payload = {"roomId": room_id, "markdown": markdown}
    r = requests.post(
        f"{WEBEX_API}/messages", headers=_headers(), json=payload, timeout=30
    )
    r.raise_for_status()
    return r.json()


def _chunk(text: str, limit: int = MAX_MESSAGE_CHARS):
    """Split long markdown on line boundaries so links never break mid-token."""
    if len(text) <= limit:
        return [text]
    chunks, buf = [], ""
    for line in text.split("\n"):
        # A single very long line: hard-split it.
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        if len(buf) + len(line) + 1 > limit:
            chunks.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        chunks.append(buf)
    return chunks


def send_markdown(room_id: str, markdown: str) -> None:
    """Post a (possibly long) markdown reply, splitting across messages."""
    chunks = _chunk(markdown)
    for i, chunk in enumerate(chunks):
        _post_message(room_id, chunk)
        if i < len(chunks) - 1:
            time.sleep(0.4)  # gentle pacing to avoid rate limits
