"""
Parse trailing model / effort / search flags off a user's message.

Single run (default Sonnet 4.6 / high effort / Claude web search):
    top 5 HPE Aruba news this week -opus 4.8 high -tavily

Compare mode (same query run across several models OR search engines):
    top 5 wifi news -compare opus 4.8 sonnet 4.6
    top 5 wifi news -compare tavily brave
    top 5 wifi news -opus 4.8 -compare tavily brave   (base = Opus, compare engines)

Recognised flags (case-insensitive, order-independent):
  model   : opus 4.8 | opus 4.7 | sonnet 4.6 | fable 5 | haiku 4.5
  effort  : high | medium | low
  search  : tavily | brave  (or claude/native for the built-in engine)
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

# Default config used when the user adds no flags.
DEFAULTS = {
    "model": "claude-sonnet-4-6",
    "model_label": "Sonnet 4.6",
    "effort": "high",
    "search": "native",
    "search_label": "Web (Claude)",
}

_FLAG_RE = re.compile(r"\s[-–—](?=[A-Za-z])")


def _parse_single(flags: str, base: dict = None) -> dict:
    """Resolve model / effort / search from a flag blob, on top of `base`."""
    cfg = dict(base or DEFAULTS)

    for key, mid, label in MODEL_ALIASES:
        if key in flags:
            cfg["model"], cfg["model_label"] = mid, label
            break

    if "high" in flags:
        cfg["effort"] = "high"
    elif "medium" in flags:
        cfg["effort"] = "medium"
    elif "low" in flags:
        cfg["effort"] = "low"

    if "tavily" in flags:
        cfg["search"], cfg["search_label"] = "tavily", SEARCH_LABELS["tavily"]
    elif "brave" in flags:
        cfg["search"], cfg["search_label"] = "brave", SEARCH_LABELS["brave"]
    elif re.search(r"\b(native|claude|web)\b", flags):
        cfg["search"], cfg["search_label"] = "native", SEARCH_LABELS["native"]

    return cfg


def _parse_variants(spec: str, base: dict) -> list:
    """Turn the text after -compare into an ordered list of run configs."""
    found = []  # (position, axis, value, label)
    for key, mid, label in MODEL_ALIASES:
        idx = spec.find(key)
        if idx != -1:
            found.append((idx, "model", mid, label))
    for key in ("tavily", "brave", "native", "claude", "web"):
        idx = spec.find(key)
        if idx != -1:
            sk = key if key in ("tavily", "brave") else "native"
            found.append((idx, "search", sk, SEARCH_LABELS[sk]))
    for eff in ("high", "medium", "low"):
        idx = spec.find(eff)
        if idx != -1:
            found.append((idx, "effort", eff, f"{eff} effort"))

    found.sort(key=lambda x: x[0])

    variants, seen = [], set()
    for _, axis, value, label in found:
        if (axis, value) in seen:
            continue
        seen.add((axis, value))
        v = dict(base)
        if axis == "model":
            v["model"], v["model_label"] = value, label
        elif axis == "search":
            v["search"], v["search_label"] = value, SEARCH_LABELS[value]
        elif axis == "effort":
            v["effort"] = value
        v["label"] = label
        variants.append(v)
    return variants[:4]  # cap the fan-out


def parse_options(text: str) -> dict:
    """Split a message into its clean query plus the chosen run config(s)."""
    m = _FLAG_RE.search(text)
    if m:
        query = text[: m.start()].strip()
        flags = text[m.start():].lower()
    else:
        query, flags = text.strip(), ""
    query = query or text.strip()

    ci = flags.find("compare")
    if ci != -1:
        base = _parse_single(flags[:ci])
        variants = _parse_variants(flags[ci + len("compare"):], base)
        if len(variants) >= 2:
            return {"query": query, "is_compare": True, "compare": variants}
        # Not enough to compare -> fall through to a single run on the base.
        cfg = base
    else:
        cfg = _parse_single(flags)

    cfg = dict(cfg)
    cfg.update({"query": query, "is_compare": False})
    return cfg
