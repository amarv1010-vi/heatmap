"""
Pluggable web-search backends for the bot's custom-search path.

Used when the user appends -tavily or -brave. The default path uses Claude's
built-in web_search server tool instead (see analyst.py) and does not need any
of these keys.
"""

import os

import requests


def tavily_search(query: str, max_results: int = 6) -> list:
    """Tavily Search API. Built for AI agents, returns clean article content."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    r = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "date": item.get("published_date", ""),
        }
        for item in data.get("results", [])
    ]


def brave_search(query: str, count: int = 6) -> list:
    """Brave Search API. General-purpose web search."""
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        raise RuntimeError("BRAVE_API_KEY is not set")
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        params={"q": query, "count": count},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("description", ""),
            "date": item.get("page_age", ""),
        }
        for item in data.get("web", {}).get("results", [])
    ]


def format_results(results: list) -> str:
    """Render search hits as plain text for the model to read."""
    if not results:
        return "No results found."
    blocks = []
    for i, r in enumerate(results, 1):
        date = f"  ({r['date']})" if r.get("date") else ""
        blocks.append(f"[{i}] {r['title']}{date}\nURL: {r['url']}\n{r['content']}")
    return "\n\n".join(blocks)
