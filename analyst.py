"""
Competitive-news analyst engine.

This is the brain of the Webex bot. It runs the bundled `competitive-news`
skill verbatim as its system prompt and hunts live news with Claude's
server-side web_search tool, so every digest follows the skill's rules:
primary-source URLs, source-confidence tags and the SDxCentral output format.
"""

import os
import functools

import anthropic

# Where the skill lives inside the repo. Kept as the single source of truth so
# the bot stays "fully aligned on the attached skill".
SKILL_DIR = os.path.join(os.path.dirname(__file__), "skill", "competitive-news")
SKILL_FILE = os.path.join(SKILL_DIR, "SKILL.md")
SOURCE_MAP_FILE = os.path.join(SKILL_DIR, "references", "source-map.md")

# A capable model is the default. Override with ANTHROPIC_MODEL if you want
# faster/cheaper runs (e.g. claude-sonnet-4-6) or the strongest (claude-opus-4-8).
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Web search budget per request. Hunting across the watchlist needs room.
MAX_WEB_SEARCHES = int(os.environ.get("MAX_WEB_SEARCHES", "12"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8000"))


@functools.lru_cache(maxsize=1)
def _load_skill() -> str:
    """Read the skill and its source map once and cache the combined prompt."""
    with open(SKILL_FILE, "r", encoding="utf-8") as fh:
        skill = fh.read()
    with open(SOURCE_MAP_FILE, "r", encoding="utf-8") as fh:
        source_map = fh.read()
    return (
        skill
        + "\n\n---\n\n# references/source-map.md\n\n"
        + source_map
    )


def _system_prompt(today: str) -> str:
    """Skill text plus the runtime framing the bot needs."""
    skill = _load_skill()
    return (
        skill
        + "\n\n---\n\n# Runtime context\n\n"
        + f"- Today's date is {today}. Treat this as 'now' for every window calculation.\n"
        + "- You are running as a Webex chatbot. The user's message is a single chat request.\n"
        + "- Use the web_search tool aggressively to hunt live. Never answer news from memory.\n"
        + "- Honour any 'top N' the user asks for (e.g. 'top 5'): return at most N stories, "
        "ranked by competitive materiality, most recent first.\n"
        + "- Honour any topic filter the user gives (e.g. 'campus networking', 'SASE', 'data center').\n"
        + "- If the user names one vendor, focus on that vendor and skip the full-watchlist sweep.\n"
        + "- Output is rendered as Webex markdown. Use the skill's digest format. Keep links as "
        "plain clickable URLs. Do not use tables.\n"
        + "- If a hunt genuinely returns nothing in the window, say 'No material news in window' "
        "rather than inventing a story."
    )


def run_analysis(user_query: str, today: str, model: str = None) -> str:
    """
    Run the competitive-news hunt for a single user query and return the
    finished digest as markdown text.

    Raises on hard API failure so the caller can report it back to the user.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = model or DEFAULT_MODEL

    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": MAX_WEB_SEARCHES,
        }
    ]

    messages = [{"role": "user", "content": user_query}]
    system = _system_prompt(today)

    # Long server-tool runs can return stop_reason "pause_turn". Continue the
    # turn until the model is done, capping iterations as a safety valve.
    for _ in range(8):
        resp = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break

    # Collect all text blocks from the final assistant turn.
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    text = "\n".join(p for p in parts if p).strip()
    return text or "I could not produce a digest for that request. Try rephrasing."
