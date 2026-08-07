"""Polymarket prediction-market data via the public Gamma API.

Crypto prediction markets are event-based "price ladder" structures: one event
(e.g. "Bitcoin above ___ on August 7?") holds many outcome markets (price
levels), each with a market-implied probability. Filtering happens at the
*event* level by 24h volume (hardcoded threshold), because single-market
filtering would keep only the one or two actively-traded levels and lose the
probability curve. Within an event, low-volume levels are dropped so the
LLM is not fed noise.
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

_POLYMARKET_EVENTS_URL = "https://gamma-api.polymarket.com/events"
_TAG_SLUG = "crypto"

# Event-level hardcoded threshold: keeps the BTC/ETH mainline events and drops
# low-participation ones (verified: $100k retains ~6 events, $90k-and-below are
# thin). Not exposed as config by design.
MIN_EVENT_VOL24 = 100_000
MAX_EVENTS = 10
MAX_MARKETS_PER_EVENT = 12
MIN_MARKET_VOL24 = 1


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_json_list(raw: Any) -> list[str]:
    """Parse the ``outcomes``/``outcomePrices`` fields, which are JSON strings."""
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _matches_coin(coin_query: str, event_title: str, questions: list[str]) -> bool:
    """True when any meaningful token of ``coin_query`` (e.g. ``Bitcoin BTC``) matches.

    One-letter tokens are dropped so a query like "Magnificent 7" cannot match
    an event titled "...August 7?" via the bare digit "7".
    """
    tokens = [t for t in coin_query.split() if len(t) >= 2]
    if not tokens:
        return False
    title = event_title.lower()
    texts = [title] + [q.lower() for q in questions]
    return any(token.lower() in text for token in tokens for text in texts)


def _normalize_market(market: dict[str, Any]) -> dict[str, Any] | None:
    vol24 = _as_float(market.get("volume24hr"))
    if vol24 < MIN_MARKET_VOL24:
        return None
    return {
        "question": market.get("question", ""),
        "outcomes": _parse_json_list(market.get("outcomes")),
        "prices": _parse_json_list(market.get("outcomePrices")),
        "volume24hr": vol24,
        "liquidity": _as_float(market.get("liquidity")),
        "end_date": market.get("endDate", ""),
    }


def _normalize_event(event: dict[str, Any], coin_query: str) -> dict[str, Any] | None:
    markets_raw = event.get("markets")
    if not isinstance(markets_raw, list):
        return None
    markets = [m for m in (_normalize_market(m) for m in markets_raw) if m is not None]
    if not markets:
        return None
    questions = [m["question"] for m in markets]
    if not _matches_coin(coin_query, event.get("title", ""), questions):
        return None
    event_vol24 = sum(m["volume24hr"] for m in markets)
    if event_vol24 < MIN_EVENT_VOL24:
        return None
    markets.sort(key=lambda m: m["volume24hr"], reverse=True)
    return {
        "title": event.get("title", ""),
        "end_date": event.get("endDate", ""),
        "event_vol24": event_vol24,
        "markets": markets[:MAX_MARKETS_PER_EVENT],
    }


async def fetch_crypto_events(coin_query: str) -> list[dict[str, Any]]:
    """Fetch Polymarket crypto events matching ``coin_query``.

    Returns a list of normalized events (title / end_date / event_vol24 /
    markets with question, outcomes, prices, volume24hr, liquidity), newest
    active markets first. Returns an empty list on any failure so callers can
    treat "no signal" gracefully.
    """

    params = {
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": str(MAX_EVENTS),
        "tag_slug": _TAG_SLUG,
    }
    timeout = aiohttp.ClientTimeout(total=12)
    try:
        async with (
            aiohttp.ClientSession(trust_env=True) as session,
            session.get(_POLYMARKET_EVENTS_URL, params=params, timeout=timeout) as resp,
        ):
            if resp.status != 200:
                return []
            payload = await resp.json()
    except (TimeoutError, aiohttp.ClientError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    events = [
        normalized
        for normalized in (_normalize_event(e, coin_query) for e in payload)
        if normalized is not None
    ]
    events.sort(key=lambda e: e["event_vol24"], reverse=True)
    return events
