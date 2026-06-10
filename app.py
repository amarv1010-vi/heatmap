"""
Webex bot: Competitors News.

Receives Webex `messages:created` webhooks, runs the competitive-news skill
against the request with live web search, and posts the digest back into the
space. Long hunts run in a background thread so the webhook returns fast.
"""

import os
import re
import hmac
import hashlib
import datetime
import threading

from dotenv import load_dotenv
from flask import Flask, request, jsonify

# Load secrets from a local .env file if present (no-op in cloud hosts that set
# real environment variables).
load_dotenv()

import webex_client
from analyst import run_analysis
from options import parse_options

app = Flask(__name__)

# Cached bot identity so we can ignore the bot's own messages and strip its
# @mention from incoming text.
_BOT = None


def bot_identity() -> dict:
    global _BOT
    if _BOT is None:
        _BOT = webex_client.get_me()
    return _BOT


def _verify_signature(raw_body: bytes) -> bool:
    """
    If WEBEX_WEBHOOK_SECRET is set, enforce Webex's X-Spark-Signature
    (HMAC-SHA1 of the raw body). If no secret is configured, skip the check.
    """
    secret = os.environ.get("WEBEX_WEBHOOK_SECRET")
    if not secret:
        return True
    sig = request.headers.get("X-Spark-Signature", "")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(sig, expected)


def _strip_mention(text: str) -> str:
    """Remove the bot's display name from the start of a group-room message."""
    name = bot_identity().get("displayName", "")
    cleaned = text.strip()
    # In group rooms Webex prepends the bot's display name to the plain text.
    cleaned = re.sub(r"^@?" + re.escape(name) + r"[\s:,-]*", "", cleaned, flags=re.I)
    return cleaned.strip()


HELP_TEXT = (
    "**Competitors News** — your SDxCentral-grade networking CI analyst.\n\n"
    "Ask me things like:\n"
    "- `look for top 5 HPE Aruba news this week in campus networking`\n"
    "- `what's new with Juniper since last week`\n"
    "- `any data center announcements from Arista in the last 24h`\n\n"
    "**Optional flags** (add at the end of your question):\n"
    "- Model: `-opus 4.8` · `-opus 4.7` · `-sonnet 4.6` · `-fable 5` · `-haiku 4.5`\n"
    "- Effort: `high` · `medium` · `low` (deeper reasoning = higher)\n"
    "- Search: `-tavily` · `-brave` (default is Claude web search)\n"
    "- Example: `top 5 Fortinet SASE news this week -opus 4.8 high -tavily`\n\n"
    "Default with no flags: Sonnet 4.6, medium effort, Claude web search.\n\n"
    "I hunt primary sources first, date every story, tag confidence "
    "([VERIFIED]/[INFERRED]/[UNVERIFIED]/[STALE]) and give you a clickable "
    "URL for every claim. Watchlist: Cisco, Huawei (+eKit), HPE Aruba, Juniper, "
    "Nokia, Extreme, Arista, Ubiquiti, Tellabs, Meter, Nile, Fortinet."
)


def _process(message_id: str):
    """Background worker: read the request, run the hunt, post the digest."""
    try:
        msg = webex_client.get_message(message_id)
        room_id = msg["roomId"]
        raw = _strip_mention(msg.get("text", ""))

        if not raw or raw.lower() in {"help", "hi", "hello", "start"}:
            webex_client.send_markdown(room_id, HELP_TEXT)
            return

        opts = parse_options(raw)
        query = opts["query"]
        used = (
            f"🧠 {opts['model_label']} · {opts['effort']} effort · "
            f"🔎 {opts['search_label']}"
        )

        webex_client.send_markdown(
            room_id,
            f"🔎 Hunting: _{query}_\n{used}\nWorking the sources, give me a moment…",
        )

        today = datetime.date.today().isoformat()
        digest = run_analysis(
            query,
            today=today,
            model=opts["model"],
            effort=opts["effort"],
            search=opts["search"],
        )
        webex_client.send_markdown(room_id, f"**{used}**\n\n{digest}")
    except Exception as exc:  # surface failures to the user, never go silent
        try:
            room_id = webex_client.get_message(message_id)["roomId"]
            webex_client.send_markdown(
                room_id, f"⚠️ I hit an error running that hunt: `{exc}`"
            )
        except Exception:
            app.logger.exception("Failed to process message %s", message_id)


@app.route("/", methods=["GET"])
def health():
    return jsonify(status="ok", bot="Competitors News")


@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data()
    if not _verify_signature(raw):
        return jsonify(error="bad signature"), 403

    data = request.get_json(silent=True) or {}
    if data.get("resource") != "messages" or data.get("event") != "created":
        return jsonify(status="ignored"), 200

    payload = data.get("data", {})
    person_id = payload.get("personId")
    person_email = payload.get("personEmail", "")

    # Ignore the bot's own messages (prevents loops). Webex bot emails end in
    # @webex.bot; also compare against our own id.
    if person_email.endswith("@webex.bot") or person_id == bot_identity().get("id"):
        return jsonify(status="ignored-self"), 200

    message_id = payload.get("id")
    if message_id:
        threading.Thread(target=_process, args=(message_id,), daemon=True).start()

    # Return fast so Webex does not retry. The work happens in the thread.
    return jsonify(status="accepted"), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
