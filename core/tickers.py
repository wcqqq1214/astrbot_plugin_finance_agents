"""Resolve a raw ticker input into a stock or crypto fetch spec.

Bare crypto codes (``BTC``/``ETH``, or ``BTC-USD``/``BTC-USDT``) are recognized
via a built-in name table that the user can extend with the ``crypto_name_map``
config. Market data is fetched from ``-USD`` with ``-USDT`` as fallback; news
and X searches use the coin's full name so results match real discussion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# base symbol -> friendly name used for news/X search queries
DEFAULT_CRYPTO_NAMES: dict[str, str] = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "XRP": "XRP",
    "DOGE": "Dogecoin",
    "ADA": "Cardano",
    "BNB": "BNB",
    "AVAX": "Avalanche",
    "LTC": "Litecoin",
    "DOT": "Polkadot",
    "LINK": "Chainlink",
}

_ANCHOR_SUFFIXES = ("-USDT", "-USD")


@dataclass(frozen=True)
class TickerSpec:
    display: str
    search_query: str
    candidates: tuple[str, ...]
    is_crypto: bool


def _strip_anchor(text: str) -> str:
    for suffix in _ANCHOR_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def _clean(raw: str) -> str:
    text = (raw or "").strip().upper().strip("$")
    for token in text.split():
        cleaned = token.strip(",.;:()。，；：（）")
        if cleaned:
            return cleaned
    return text


def _crypto_names(config: dict[str, Any]) -> dict[str, str]:
    merged = dict(DEFAULT_CRYPTO_NAMES)
    extra = config.get("crypto_name_map") or {}
    if isinstance(extra, dict):
        for key, value in extra.items():
            if isinstance(value, str) and value.strip():
                merged[str(key).strip().upper()] = value.strip()
    return merged


def resolve_ticker(raw: str, config: dict[str, Any]) -> TickerSpec:
    text = _clean(raw)
    names = _crypto_names(config)
    base = _strip_anchor(text)
    if base in names:
        name = names[base]
        search_query = base if name.upper() == base else f"{name} {base}"
        return TickerSpec(
            display=base,
            search_query=search_query,
            candidates=(f"{base}-USD", f"{base}-USDT"),
            is_crypto=True,
        )
    return TickerSpec(
        display=text,
        search_query=text,
        candidates=(text,),
        is_crypto=False,
    )
