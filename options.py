"""
Parse trailing model / effort / search flags off a user's message.

Users append flags at the end after a dash, e.g.

    top 5 HPE Aruba news this week in campus networking -opus 4.8 high -tavily

Recognised flags (case-insensitive, order-independent):
  model   : opus 4.8 | opus 4.7 | sonnet 4.6 | fable 5 | haiku 4.5
  effort  : high | medium | low
  search  : tavily | brave   (omit for Claude's built-in web search)

Anything with no flags falls back to the defaults below (today's behaviour).
"""

import re

# (substring to match in the flag blob, model id, friendly label)
MODEL_ALIASES = [
    ("fable 5", "claude-fable-5", "Fable 5"),
    ("fable5", "claude-fable-5", "Fable 5"),
    ("opus 4.8", "claude-opus-4-8", "Opus 4.8"),
    ("opus4.8", "claude-opus-4-8", "Opus 4.8"),
    ("opus 4.7", "claude-opus-4-7", "Opus 4.7"),
    ("opus4.7", "claude-opus-4-7", "Opus 4.7"),
    ("sonnet 4.6", "claude-sonnet-4-6", "Sonnet 4.6"),
    ("sonnet4.6", "claude-sonnet-4-6", "Sonnet 4.6"),
    ("haiku 4.5", "claude-haiku-4-5-20251001", "Haiku 4.5"),
    ("haiku4.5", "claude-haiku-4-5-20251001", "Haiku 4.5"),
]

SEARCH_LABELS = {"native": "Web (Claude)", "tavily": "Tavily", "brave": "Brave"}

DEFAULTS = {
    "model": "claude-sonnet-4-6",
    "model_label": "Sonnet 4.6",
    "effort": "medium",
    "search": "native",
}


def parse_options(text: str) -> dict:
    """Split a message into its clean query plus the chosen model/effort/search."""
    # The flag section starts at the first " -word" (space, dash, letter).
    m = re.search(r"\s[-–—](?=[A-Za-z])", text)
    if m:
        query = text[: m.start()].strip()
        flags = text[m.start():].lower()
    else:
        query, flags = text.strip(), ""

    model, model_label = DEFAULTS["model"], DEFAULTS["model_label"]
    for key, mid, label in MODEL_ALIASES:
        if key in flags:
            model, model_label = mid, label
            break

    if "high" in flags:
        effort = "high"
    elif "medium" in flags:
        effort = "medium"
    elif "low" in flags:
        effort = "low"
    else:
        effort = DEFAULTS["effort"]

    if "tavily" in flags:
        search = "tavily"
    elif "brave" in flags:
        search = "brave"
    else:
        search = DEFAULTS["search"]

    return {
        "query": query or text.strip(),
        "model": model,
        "model_label": model_label,
        "effort": effort,
        "search": search,
        "search_label": SEARCH_LABELS[search],
    }
