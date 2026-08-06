"""Market data via yfinance, run in a worker thread.

yfinance is synchronous and network-bound, so every call is wrapped in
``asyncio.to_thread`` to keep the plugin's event loop responsive.
"""

from __future__ import annotations

import asyncio
from typing import Any

import yfinance as yf


def _compute_indicators(df: Any) -> dict[str, Any]:
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
