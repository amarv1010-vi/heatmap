# Competitors News — Webex Bot

A Webex Teams chatbot that hunts networking-OEM competitive intelligence the way
a senior SDxCentral analyst would. @mention it in a space (or DM it) with a
request and it runs the bundled **`competitive-news` skill** end to end — live
web hunt, primary-source URLs, source-confidence tags, dated stories, and an
SDxCentral-style digest — then posts the answer back into the space.

```
@Competitors News look for top 5 HPE Aruba news this week in campus networking
```

The bot is **fully aligned on the attached skill**: `skill/competitive-news/`
is the verbatim skill, loaded as the model's system prompt at runtime, so the
watchlist, timeline discipline, hunt order, source map, confidence tagging and
output format all come straight from it. There is no second copy of the rules to
drift out of sync.

---

## How it works

```
Webex space
   │  (you @mention the bot)
   ▼
messages:created webhook  ──►  app.py (Flask)
                                 │  returns 200 fast, works in a thread
                                 ▼
                              analyst.py
                                 │  system prompt = SKILL.md + source-map.md
                                 │  tool = Claude web_search (live hunt)
                                 ▼
                              digest text
                                 │
                              webex_client.py  ──►  posts back to the space
```

- **`app.py`** — Flask webhook server. Validates the event, ignores the bot's
  own messages (no loops), strips the @mention, acks instantly with
  `🔎 Hunting…`, then runs the hunt in a background thread.
- **`analyst.py`** — the engine. Loads the skill as the system prompt and calls
  Claude with the server-side `web_search` tool so news is hunted live, never
  recalled from memory.
- **`webex_client.py`** — minimal Webex Messages API client. Chunks long
  digests to stay under Webex's per-message size limit.
- **`setup_webhook.py`** — registers the webhook with Webex (run once your URL
  is public).
- **`local_test.py`** — run the analyst straight from the terminal, no Webex.
- **`skill/competitive-news/`** — the skill itself (the bot's brain).

---

## Prerequisites

| What | Where |
|---|---|
| **Webex Bot Access Token** | You already created the bot `Competitors News` (`Cnews@webex.bot`) at developer.webex.com. Copy its **Bot Access Token**. If you lost it, regenerate it on the bot's page. |
| **Anthropic API key** | console.anthropic.com → API keys. Powers the analyst + web search. |
| **A public HTTPS URL** | Webex must reach your `/webhook`. Use a host (Render/Railway/Fly/Heroku/your server) or `ngrok` for local testing. |

---

## Quick start (local, with ngrok)

```bash
# 1. install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. configure
cp .env.example .env
#   edit .env: WEBEX_BOT_TOKEN, ANTHROPIC_API_KEY

# 3. smoke-test the brain with NO Webex needed
export ANTHROPIC_API_KEY=sk-ant-...
python local_test.py "top 5 HPE Aruba news this week in campus networking"

# 4. run the server
set -a && source .env && set +a
python app.py            # serves on http://localhost:5000

# 5. expose it and register the webhook (new terminal)
ngrok http 5000          # copy the https URL it prints
export WEBEX_BOT_TOKEN=...     # same token as in .env
export TARGET_URL=https://<your-ngrok-subdomain>.ngrok.io/webhook
python setup_webhook.py
```

Now add the bot to a Webex space and `@Competitors News help`, or DM it.

---

## Deploy (production)

Any container/PaaS host works. The repo includes a `Dockerfile` and a `Procfile`.

**Render / Railway / Fly / Heroku (Procfile or Docker):**

1. Push this branch and create a service from the repo.
2. Set env vars: `WEBEX_BOT_TOKEN`, `ANTHROPIC_API_KEY`, and optionally
   `WEBEX_WEBHOOK_SECRET`, `ANTHROPIC_MODEL`.
3. Deploy. Note the public HTTPS URL.
4. Register the webhook against the live URL:
   ```bash
   WEBEX_BOT_TOKEN=...  TARGET_URL=https://<your-app>/webhook  python setup_webhook.py
   ```

**Docker directly:**

```bash
docker build -t competitors-news .
docker run -p 8080:8080 \
  -e WEBEX_BOT_TOKEN=... -e ANTHROPIC_API_KEY=... \
  competitors-news
```

> Hunts that sweep the full watchlist can take a minute or two. The server is
> configured with a 180s worker timeout and the webhook returns immediately, so
> Webex never times out waiting.

---

## Using the bot

In **group spaces** you must @mention the bot. In a **1:1 direct message** just
type. Examples:

- `look for top 5 HPE Aruba news this week in campus networking`
- `what's new with Juniper since last week`
- `any data center announcements from Arista in the last 24h`
- `help`

Every story comes back dated, with a clickable primary-source URL and a
confidence tag: `[VERIFIED]` / `[INFERRED]` / `[UNVERIFIED]` / `[STALE]`.

### Picking a model and search engine

Append flags at the **end** of any message (after a dash). Order does not matter.

| Flag group | Options |
|---|---|
| Model | `-opus 4.8` · `-opus 4.7` · `-sonnet 4.6` · `-fable 5` · `-haiku 4.5` |
| Effort | `high` · `medium` · `low` (more effort = deeper reasoning budget) |
| Search | `-tavily` · `-brave` (omit for Claude's built-in web search) |

Examples:
- `top 5 Fortinet SASE news this week -opus 4.8 -tavily`
- `whats new with Juniper -sonnet 4.6 medium`
- `Arista campus push -fable 5 -brave`

No flags → **Sonnet 4.6, high effort, Claude web search** (the default).

### Compare mode

Run the same query side by side across models or search engines with `-compare`:

- `top 5 wifi news -compare opus 4.8 sonnet 4.6` — compare two models
- `top 5 wifi news -compare tavily brave` — compare two search engines
- `top 5 wifi news -opus 4.8 -compare tavily brave` — hold model at Opus, compare engines

Each variant runs in parallel and posts as its own labelled digest (max 4 variants).

To use `-tavily` or `-brave`, set `TAVILY_API_KEY` / `BRAVE_API_KEY` in Render's
Environment Variables (see `.env.example`). Tavily is recommended for news.

---

## Security notes

- Set `WEBEX_WEBHOOK_SECRET` (and pass the same value to `setup_webhook.py`) to
  enforce Webex's `X-Spark-Signature` HMAC on every inbound webhook.
- The bot ignores messages from any `@webex.bot` sender and its own id, so it
  cannot loop on itself.
- Secrets live only in env vars / `.env`, which is git-ignored.

---

## App Hub submission

If you later want to list this in the Webex App Hub
(developer.webex.com/create/docs/app-hub-submission-process), the basics it
expects are already satisfiable here: a stable public webhook endpoint, a clear
bot description and help command, no storage of message content beyond the live
request, and a privacy/usage note. Add a logo (512x512), a support contact, and
a short listing description, then submit from your developer account
(`amarprsi@cisco.com`). Note App Hub review expects production-grade hosting and
uptime, so deploy to a managed host before submitting rather than ngrok.

---

## Configuration reference

| Env var | Default | Purpose |
|---|---|---|
| `WEBEX_BOT_TOKEN` | — | Bot Access Token (required) |
| `ANTHROPIC_API_KEY` | — | Anthropic key for the analyst (required) |
| `WEBEX_WEBHOOK_SECRET` | _(off)_ | Enables webhook signature verification |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Set to `claude-opus-4-8` for the strongest hunts |
| `MAX_WEB_SEARCHES` | `12` | Web-search budget per request |
| `MAX_TOKENS` | `8000` | Max output tokens for the digest |
| `PORT` | `5000` | Local server port |
