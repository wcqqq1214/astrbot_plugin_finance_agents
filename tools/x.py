"""X (Twitter) post retrieval via Tavily restricted to x.com.

Tavily's ``start_date`` filtering is unreliable for X posts, so the recency
bound is enforced by the social agent (each post embeds its timestamp in the
text). We still send ``start_date`` as a best-effort server-side hint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .tavily import tavily_search


def _author_handle(url: str) -> str:
    """Extract the account handle from an x.com/twitter.com status URL."""

    parts = [part for part in url.split("/") if part]
    for i, part in enumerate(parts):
        if part in ("x.com", "twitter.com") and i + 1 < len(parts):
            return parts[i + 1]
    return ""


async def search_x_posts(
    api_key: str,
    query: str,
    *,
    max_results: int = 8,
    days_back: int = 7,
) -> list[dict[str, Any]]:
    """Search recent X posts about ``query`` and return normalized items."""

    start_date = (datetime.now(UTC).date() - timedelta(days=days_back)).isoformat()
    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "topic": "general",
        "include_favicon": False,
        "include_domains": ["x.com"],
        "start_date": start_date,
    }
    results = await tavily_search(api_key, payload)
    posts = [
        {**item, "author": _author_handle(item.get("url", ""))}
        for item in results
        if "x.com" in item.get("url", "") or "twitter.com" in item.get("url", "")
    ]
    return posts[:max_results]
