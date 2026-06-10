"""
Competitive-news analyst engine.

Runs the bundled `competitive-news` skill verbatim as its system prompt and
hunts live news. Supports a choice of model, reasoning effort and search engine
(Claude's built-in web search, Tavily or Brave), all selectable per request.
"""

import os
import functools
from concurrent.futures import ThreadPoolExecutor

import anthropic

import search_providers

SKILL_DIR = os.path.join(os.path.dirname(__file__), "skill", "competitive-news")
SKILL_FILE = os.path.join(SKILL_DIR, "SKILL.md")
SOURCE_MAP_FILE = os.path.join(SKILL_DIR, "references", "source-map.md")

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

MAX_WEB_SEARCHES = int(os.environ.get("MAX_WEB_SEARCHES", "12"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8000"))
MAX_AGENT_TURNS = int(os.environ.get("MAX_AGENT_TURNS", "12"))

# Reasoning effort -> extended-thinking token budget. 0 disables thinking.
EFFORT_BUDGET = {"high": 5000, "medium": 2000, "low": 0}

# Custom client-side search tool, used for the Tavily / Brave paths.
SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the live web for current information. Returns titles, URLs and "
        "content snippets. Call it repeatedly to hunt widely across primary "
        "sources, then go deep on what matters."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"}
        },
        "required": ["query"],
    },
}


@functools.lru_cache(maxsize=1)
def _load_skill() -> str:
    with open(SKILL_FILE, "r", encoding="utf-8") as fh:
        skill = fh.read()
    with open(SOURCE_MAP_FILE, "r", encoding="utf-8") as fh:
        source_map = fh.read()
    return skill + "\n\n---\n\n# references/source-map.md\n\n" + source_map


def _system_prompt(today: str) -> str:
    skill = _load_skill()
    return (
        skill
        + "\n\n---\n\n# Runtime context\n\n"
        + f"- Today's date is {today}. Treat this as 'now' for every window calculation.\n"
        + "- You are running as a Webex chatbot. The user's message is a single chat request.\n"
        + "- Use the web_search tool aggressively to hunt live. Never answer news from memory.\n"
        + "- Honour any 'top N' the user asks for: return at most N stories, ranked by "
        "competitive materiality, most recent first.\n"
        + "- Honour any topic filter the user gives (e.g. 'campus networking', 'SASE').\n"
        + "- If the user names one vendor, focus on that vendor and skip the full-watchlist sweep.\n"
        + "- Output is rendered as Webex markdown. Use the skill's digest format. Keep links as "
        "plain clickable URLs. Do not use tables.\n"
        + "- If a hunt genuinely returns nothing in the window, say 'No material news in window' "
        "rather than inventing a story."
    )


def _thinking_and_max(effort: str):
    budget = EFFORT_BUDGET.get(effort, 0)
    if budget <= 0:
        return None, MAX_TOKENS
    return {"type": "enabled", "budget_tokens": budget}, budget + MAX_TOKENS


def _extract_text(resp) -> str:
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    text = "\n".join(p for p in parts if p).strip()
    return text or "I could not produce a digest for that request. Try rephrasing."


def _run_native(client, model, system, query, thinking, max_tokens) -> str:
    """Claude's built-in web_search server tool. Default path."""
    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": MAX_WEB_SEARCHES,
        }
    ]
    messages = [{"role": "user", "content": query}]
    resp = None
    for _ in range(8):
        kwargs = dict(
            model=model, max_tokens=max_tokens, system=system,
            tools=tools, messages=messages,
        )
        if thinking:
            kwargs["thinking"] = thinking
        resp = client.messages.create(**kwargs)
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    return _extract_text(resp)


def _run_custom(client, model, system, query, thinking, max_tokens, provider) -> str:
    """Agentic loop where the model searches via Tavily or Brave."""
    searcher = (
        search_providers.tavily_search
        if provider == "tavily"
        else search_providers.brave_search
    )
    messages = [{"role": "user", "content": query}]
    resp = None
    for _ in range(MAX_AGENT_TURNS):
        kwargs = dict(
            model=model, max_tokens=max_tokens, system=system,
            tools=[SEARCH_TOOL], messages=messages,
        )
        if thinking:
            kwargs["thinking"] = thinking
        resp = client.messages.create(**kwargs)

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use" and block.name == "web_search":
                    q = (block.input or {}).get("query", "")
                    try:
                        content = search_providers.format_results(searcher(q))
                    except Exception as exc:
                        content = f"Search error: {exc}"
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    )
            messages.append({"role": "user", "content": results})
            continue

        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    return _extract_text(resp)


def run_analysis(
    user_query: str,
    today: str,
    model: str = None,
    effort: str = "high",
    search: str = "native",
) -> str:
    """Run a single hunt and return the finished digest as markdown."""
    # Fail fast with a friendly message if a chosen engine has no key.
    if search == "tavily" and not os.environ.get("TAVILY_API_KEY"):
        return "⚠️ Tavily search isn't configured. Add `TAVILY_API_KEY` in Render to use `-tavily`."
    if search == "brave" and not os.environ.get("BRAVE_API_KEY"):
        return "⚠️ Brave search isn't configured. Add `BRAVE_API_KEY` in Render to use `-brave`."

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = model or DEFAULT_MODEL
    system = _system_prompt(today)
    thinking, max_tokens = _thinking_and_max(effort)

    if search == "native":
        return _run_native(client, model, system, user_query, thinking, max_tokens)
    return _run_custom(client, model, system, user_query, thinking, max_tokens, search)


def run_comparison(query: str, today: str, variants: list) -> list:
    """Run the same query under each variant config concurrently.

    Returns a list of (variant, digest) pairs in the original order.
    """
    def one(variant):
        try:
            digest = run_analysis(
                query,
                today=today,
                model=variant["model"],
                effort=variant["effort"],
                search=variant["search"],
            )
        except Exception as exc:
            digest = f"⚠️ Error running this variant: `{exc}`"
        return variant, digest

    with ThreadPoolExecutor(max_workers=min(len(variants), 4)) as pool:
        return list(pool.map(one, variants))
