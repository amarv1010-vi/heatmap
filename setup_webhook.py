"""
Register (or re-register) the Webex webhook that drives the bot.

Run this once after your server is reachable at a public HTTPS URL.

  WEBEX_BOT_TOKEN=...  TARGET_URL=https://your-host/webhook  python setup_webhook.py

Optional: set WEBEX_WEBHOOK_SECRET to also have app.py verify signatures.
It deletes any existing webhook with the same name first, so it is safe to
re-run whenever your public URL changes.
"""

import os
import sys

import requests

WEBEX_API = "https://webexapis.com/v1"
WEBHOOK_NAME = "competitors-news-messages"


def headers():
    token = os.environ.get("WEBEX_BOT_TOKEN")
    if not token:
        sys.exit("ERROR: set WEBEX_BOT_TOKEN")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def main():
    target = os.environ.get("TARGET_URL")
    if not target:
        sys.exit("ERROR: set TARGET_URL to your public https .../webhook endpoint")

    h = headers()

    # Remove stale webhooks with our name so re-runs do not pile up duplicates.
    existing = requests.get(f"{WEBEX_API}/webhooks", headers=h, timeout=15).json()
    for wh in existing.get("items", []):
        if wh.get("name") == WEBHOOK_NAME:
            requests.delete(f"{WEBEX_API}/webhooks/{wh['id']}", headers=h, timeout=15)
            print(f"Deleted old webhook {wh['id']}")

    payload = {
        "name": WEBHOOK_NAME,
        "targetUrl": target,
        "resource": "messages",
        "event": "created",
    }
    secret = os.environ.get("WEBEX_WEBHOOK_SECRET")
    if secret:
        payload["secret"] = secret

    r = requests.post(f"{WEBEX_API}/webhooks", headers=h, json=payload, timeout=15)
    r.raise_for_status()
    wh = r.json()
    print(f"Created webhook {wh['id']} -> {target}")
    print("Done. @mention the bot in a space or DM it to test.")


if __name__ == "__main__":
    main()
