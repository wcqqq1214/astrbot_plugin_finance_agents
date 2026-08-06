"""Market data via Binance (crypto) and yfinance (stocks).

Crypto daily OHLCV comes from Binance's public klines endpoint: no API key,
and far less rate-limited than Yahoo. Stocks keep using yfinance, which is
synchronous and network-bound, so every call is wrapped in ``asyncio.to_thread``
to keep the plugin's event loop responsive.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import pandas as pd
import yfinance as yf

_BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"
_KLINE_LIMIT = 95  # ~3 months of daily candles


def _compute_indicators(df: pd.DataFrame) -> dict[str, Any]:
    close = df["Close"]
    last_close = float(close.iloc[-1])
    sma_20 = float(close.rolling(window=20, min_periods=1).mean().iloc[-1])
    bb_std = float(close.rolling(window=20, min_periods=1).std().iloc[-1])

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_histogram = macd_line - macd_signal

    first_close = float(close.iloc[0])
    price_change_pct = (
        ((last_close - first_close) / first_close) * 100 if first_close else 0.0
    )

    return {
        "period_rows": len(df),
        "last_date": str(df.index[-1].date()),
        "last_close": last_close,
        "sma_20": sma_20,
        "macd_line": float(macd_line.iloc[-1]),
        "macd_signal": float(macd_signal.iloc[-1]),
        "macd_histogram": float(macd_histogram.iloc[-1]),
        "bb_middle": sma_20,
        "bb_upper": sma_20 + 2 * bb_std,
        "bb_lower": sma_20 - 2 * bb_std,
        "price_change_pct": price_change_pct,
    }


async def _fetch_binance_ohlcv(symbol: str) -> pd.DataFrame | None:
    """Fetch daily OHLCV for ``symbol`` (e.g. ``BTCUSDT``) from Binance.

    Returns a DataFrame indexed by UTC date with Open/High/Low/Close/Volume
    columns, or None when the request fails (network error, invalid symbol, or
    the API returning no rows).
    """

    params = {"symbol": symbol, "interval": "1d", "limit": str(_KLINE_LIMIT)}
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with (
            aiohttp.ClientSession(trust_env=True) as session,
            session.get(_BINANCE_KLINE_URL, params=params, timeout=timeout) as resp,
        ):
            if resp.status != 200:
                return None
            payload = await resp.json()
    except (TimeoutError, aiohttp.ClientError):
        return None
    if not isinstance(payload, list):
        return None
    rows = [
        (int(r[0]), r[1], r[2], r[3], r[4], r[5])
        for r in payload
        if isinstance(r, list) and len(r) >= 6
    ]
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df.set_index("ts").sort_index()


def _fetch_indicators_sync(ticker: str) -> dict[str, Any]:
    try:
        hist = yf.Ticker(ticker).history(period="3mo", interval="1d", auto_adjust=True)
    except Exception as exc:  # noqa: BLE001 - yfinance raises many provider-specific errors
        return {"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"}
    if hist is None or hist.empty:
        return {"ticker": ticker, "error": f"No market data found for {ticker}."}
    df = hist.dropna(subset=["Close"])
    if df.empty:
        return {"ticker": ticker, "error": f"No market data found for {ticker}."}
    out = _compute_indicators(df)
    out["ticker"] = ticker
    return out


async def fetch_indicators(ticker: str) -> dict[str, Any]:
    """Return a technical indicators snapshot for ``ticker``."""

    return await asyncio.to_thread(_fetch_indicators_sync, ticker)


async def fetch_first_available(candidates: list[str]) -> dict[str, Any]:
    """Fetch indicators from ``candidates`` in order, returning the first hit."""

    last_error = ""
    for symbol in candidates:
        result = await fetch_indicators(symbol)
        if "error" not in result:
            return result
        last_error = result["error"]
    return {
        "ticker": candidates[0] if candidates else "",
        "error": f"None of {', '.join(candidates)} returned data: {last_error}",
    }


async def fetch_crypto_indicators(base: str) -> dict[str, Any]:
    """Return a technical indicators snapshot for crypto ``base`` (e.g. ``BTC``).

    Data comes exclusively from Binance's ``{base}USDT`` pair; no fallback.
    """

    df = await _fetch_binance_ohlcv(f"{base}USDT")
    if df is None or df.empty:
        return {
            "ticker": f"{base}-USDT",
            "error": f"No market data from Binance for {base}USDT.",
        }
    out = _compute_indicators(df)
    out["ticker"] = f"{base}-USDT"
    out["provider"] = "binance"
    return out
