"""News retrieval via Tavily's news topic."""

from __future__ import annotations

from typing import Any

from .tavily import tavily_search


async def search_news(
    api_key: str,
    query: str,
    *,
    days: int = 7,
    max_results: int = 8,
) -> list[dict[str, Any]]:
    """Search recent news about ``query`` and return normalized items."""

    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "topic": "news",
        "days": days,
        "include_favicon": False,
    }
    results = await tavily_search(api_key, payload)
    return results[:max_results]
