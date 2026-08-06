"""Minimal Tavily search client.

Reads the same API keys the user configures for AstrBot's built-in web search
(``provider_settings.websearch_tavily_key``), so the plugin needs no extra key
setup. ``include_domains`` is supported directly, which the built-in tool does
not expose — this is how we can pull X (Twitter) posts.
"""

from __future__ import annotations

from typing import Any

import aiohttp

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_RETRYABLE_STATUSES = frozenset({401, 403, 429, 432})


class TavilyError(Exception):
    """Raised when a Tavily request fails."""


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    url = item.get("url") or ""
    source = item.get("source") or ""
    if not source and url:
        source = url.replace("https://", "").replace("http://", "")
        source = source.split("/")[0].replace("www.", "")
    return {
        "title": item.get("title") or "",
        "url": url,
        "snippet": item.get("content") or "",
        "source": source,
        "published_time": item.get("published_date") or "",
    }


async def tavily_search(api_key: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """POST one search to Tavily and return normalized results.

    Raises:
        TavilyError: If the request fails after all retryable keys are
            exhausted or a non-retryable HTTP status is returned.
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error: Exception | None = None
    for _ in range(3):
        async with (
            aiohttp.ClientSession(trust_env=True) as session,
            session.post(_TAVILY_SEARCH_URL, json=payload, headers=headers) as response,
        ):
            if response.status == 200:
                data = await response.json()
                return [_normalize(item) for item in data.get("results", [])]
            reason = await response.text()
            if response.status in _RETRYABLE_STATUSES:
                last_error = TavilyError(
                    f"Tavily search failed: {reason}, status: {response.status}"
                )
                continue
            raise TavilyError(
                f"Tavily search failed: {reason}, status: {response.status}"
            )
    if last_error is not None:
        raise last_error
    raise TavilyError("Tavily search failed.")
