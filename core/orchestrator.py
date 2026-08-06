"""Parallel multi-agent orchestration.

Runs quant / news / social research in parallel (``asyncio.gather``), then a
single CIO call folds the three reports into a bull/bear/verdict JSON (the "2a"
variant). ``on_progress`` is invoked as each stage transitions so the Star can
stream live progress to the chat.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from astrbot.api import logger

from ..tools import market as market_tool
from ..tools import news as news_tool
from ..tools import x as x_tool
from . import prompts
from .formatting import format_news_block, format_quant_block, format_social_block
from .llm import LLMAdapter, create_llm
from .parsing import extract_json_object
from .tickers import resolve_ticker
from .types import (
    AnalysisResult,
    CIOVerdict,
    NewsReport,
    QuantReport,
    SocialReport,
)

ProgressCallback = Callable[[str, str, str], Awaitable[None]]

BIAS_VALUES = ("bullish", "bearish", "neutral")


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _bias(value: Any, default: str = "neutral") -> str:
    return value if value in BIAS_VALUES else default


def _detect_lang(text: str) -> str:
    """Return 'Chinese' when the query contains CJK characters, else 'English'."""

    return "Chinese" if any("一" <= ch <= "鿿" for ch in text) else "English"


# --- deterministic fallbacks (used when the LLM output cannot be parsed) ---


def _fallback_trend(indicators: dict[str, Any]) -> str:
    last = indicators.get("last_close")
    sma = indicators.get("sma_20")
    if last is None or sma is None:
        return "neutral"
    if last > sma:
        return "bullish"
    if last < sma:
        return "bearish"
    return "neutral"


def _fallback_levels(indicators: dict[str, Any]) -> dict[str, Any]:
    last = indicators.get("last_close")
    return {
        "support": indicators.get("bb_lower") or last,
        "resistance": indicators.get("bb_upper") or last,
    }


def _fallback_summary(trend: str, indicators: dict[str, Any]) -> str:
    last = indicators.get("last_close")
    if last is not None:
        return f"自动兜底结论：现价 {last:.2f}，技术面 {trend}。"
    return "自动兜底结论：暂无行情数据。"


# --- research agents ---


async def quant_agent(
    llm: LLMAdapter,
    ticker: str,
    indicators_coro: Awaitable[dict[str, Any]],
    *,
    lang: str,
) -> QuantReport:
    indicators = await indicators_coro
    if "error" in indicators:
        return {
            "asset": ticker,
            "trend": "neutral",
            "indicators": {},
            "levels": {},
            "summary": f"行情数据获取失败：{indicators['error']}",
        }
    user_content = (
        f"Asset: {ticker}\n\nTechnical indicators snapshot (JSON):\n"
        f"{json.dumps(indicators, ensure_ascii=False)}"
    )
    text = await llm.chat(prompts.quant_system(lang), user_content)
    try:
        obj = extract_json_object(text)
    except ValueError:
        obj = {}
    trend = _bias(obj.get("trend"), _fallback_trend(indicators))
    levels = (
        obj.get("levels")
        if isinstance(obj.get("levels"), dict)
        else _fallback_levels(indicators)
    )
    summary = _str(obj.get("summary")) or _fallback_summary(trend, indicators)
    return {
        "asset": ticker,
        "trend": trend,
        "indicators": indicators,
        "levels": levels,
        "summary": summary,
    }


async def news_agent(
    llm: LLMAdapter,
    ticker: str,
    api_key: str,
    *,
    query: str,
    days: int,
    max_results: int,
    lang: str,
) -> NewsReport:
    articles = await news_tool.search_news(
        api_key, query, days=days, max_results=max_results
    )
    if not articles:
        return {
            "asset": ticker,
            "bias": "neutral",
            "key_points": ["未检索到近期相关新闻。"],
            "sources": [],
        }
    user_content = (
        f"Asset: {ticker}\n\nRecent news items (JSON):\n"
        f"{json.dumps(articles, ensure_ascii=False)}"
    )
    text = await llm.chat(prompts.news_system(lang), user_content)
    try:
        obj = extract_json_object(text)
    except ValueError:
        obj = {}
    key_points = [
        item
        for item in (obj.get("key_points") or [])
        if isinstance(item, str) and item.strip()
    ][:6]
    if not key_points:
        key_points = [f"检索到 {len(articles)} 条相关新闻。"]
    return {
        "asset": ticker,
        "bias": _bias(obj.get("bias")),
        "key_points": key_points,
        "sources": articles,
    }


async def social_agent(
    llm: LLMAdapter,
    ticker: str,
    api_key: str,
    *,
    query: str,
    max_results: int,
    days_back: int,
    lang: str,
    min_posts: int,
) -> SocialReport:
    posts = await x_tool.search_x_posts(
        api_key, query, max_results=max_results, days_back=days_back
    )
    if not posts:
        return {
            "asset": ticker,
            "sentiment": "neutral",
            "signal_available": False,
            "coverage_status": "unavailable",
            "summary": "未检索到近期 X 帖子。",
            "posts": [],
        }
    user_content = (
        f"Asset: {ticker}\n\nRecent X posts (JSON):\n"
        f"{json.dumps(posts, ensure_ascii=False)}"
    )
    text = await llm.chat(prompts.social_system(lang, min_posts), user_content)
    try:
        obj = extract_json_object(text)
    except ValueError:
        obj = {}
    signal_available = bool(obj.get("signal_available", True))
    if len(posts) < min_posts:
        signal_available = False
    summary = _str(obj.get("summary"))
    if not summary:
        summary = (
            "未检索到足够的近期 X 帖子。"
            if not signal_available
            else f"检索到 {len(posts)} 条 X 帖子。"
        )
    return {
        "asset": ticker,
        "sentiment": _bias(obj.get("sentiment")),
        "signal_available": signal_available,
        "coverage_status": "available" if signal_available else "unavailable",
        "summary": summary,
        "posts": posts,
    }


async def cio_agent(
    llm: LLMAdapter,
    ticker: str,
    query: str,
    quant: QuantReport,
    news: NewsReport,
    social: SocialReport,
) -> CIOVerdict:
    block = "\n\n".join(
        [
            f"User question:\n{query}",
            format_quant_block(quant),
            format_news_block(news),
            format_social_block(social),
        ]
    )
    text = await llm.chat(prompts.cio_system(), block)
    try:
        obj = extract_json_object(text)
    except ValueError:
        obj = {}
    bull_case = _str(obj.get("bull_case")) or "（无）"
    bear_case = _str(obj.get("bear_case")) or "（无）"
    final_decision = _str(obj.get("final_decision"))
    if not final_decision:
        final_decision = f"综合结论：\n{bull_case}\n\n主要风险：\n{bear_case}"
    final_summary = _str(obj.get("final_summary"))
    if not final_summary:
        final_summary = "综合多空双方后方向尚不明确，建议观望。"
    return {
        "asset": ticker,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "final_decision": final_decision,
        "final_summary": final_summary,
    }


# --- entry point ---


async def run_analysis(
    context: Any,
    umo: str,
    config: dict[str, Any],
    ticker_raw: str,
    query: str,
    *,
    on_progress: ProgressCallback | None = None,
) -> AnalysisResult:
    spec = resolve_ticker(ticker_raw, config)
    ticker = spec.display
    llm = create_llm(context, umo)
    lang = _detect_lang(query)
    api_key = _str(config.get("tavily_api_key")) or None
    twelve_data_key = _str(config.get("twelve_data_api_key")) or None
    timeout = int(config.get("agent_timeout", 90) or 90)
    news_days = int(config.get("news_days", 7) or 7)
    max_results = int(config.get("max_results", 8) or 8)
    x_search_enabled = bool(config.get("x_search_enabled", True))
    x_search_days = int(config.get("x_search_days", 7) or 7)
    x_min_posts = int(config.get("x_min_posts", 3) or 3)

    async def _task(
        label: str,
        running_msg: str,
        done_msg: str,
        coro: Awaitable[Any],
    ) -> Any:
        if on_progress is not None:
            await on_progress(label, "running", running_msg)
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            if on_progress is not None:
                await on_progress(
                    label, "timeout", f"⏱️ {label} 超时（>{timeout}s），已跳过"
                )
            return None
        except Exception as exc:  # noqa: BLE001 - a failing agent must not break the run
            logger.error("Agent %s failed: %s", label, exc, exc_info=True)
            if on_progress is not None:
                await on_progress(
                    label, "error", f"⚠️ {label} 失败：{type(exc).__name__}"
                )
            return None
        if on_progress is not None:
            await on_progress(label, "done", done_msg)
        return result

    quant_fetch = (
        market_tool.fetch_crypto_indicators(spec.display)
        if spec.is_crypto
        else market_tool.fetch_stock_indicators(spec.display, twelve_data_key)
    )
    tasks: list[Awaitable[Any]] = [
        _task(
            "quant",
            "📊 量化技术面分析中…",
            "✅ 量化技术面分析完成",
            quant_agent(llm, ticker, quant_fetch, lang=lang),
        )
    ]
    if api_key:
        tasks.append(
            _task(
                "news",
                "📰 新闻情绪分析中…",
                "✅ 新闻情绪分析完成",
                news_agent(
                    llm,
                    ticker,
                    api_key,
                    query=spec.search_query,
                    days=news_days,
                    max_results=max_results,
                    lang=lang,
                ),
            )
        )
        if x_search_enabled:
            tasks.append(
                _task(
                    "social",
                    "🐦 X 社交情绪分析中…",
                    "✅ X 社交情绪分析完成",
                    social_agent(
                        llm,
                        ticker,
                        api_key,
                        query=spec.search_query,
                        max_results=max_results,
                        days_back=x_search_days,
                        lang=lang,
                        min_posts=x_min_posts,
                    ),
                )
            )
        else:
            if on_progress is not None:
                await on_progress("social", "skipped", "ℹ️ 已关闭 X 帖子分析（配置项）")
    else:
        if on_progress is not None:
            await on_progress(
                "news",
                "skipped",
                "⚠️ 未配置 Tavily Key，跳过新闻与 X 分析（请在插件配置中填写 tavily_api_key）",
            )

    results = await asyncio.gather(*tasks)
    quant = results[0] if len(results) > 0 else None
    news = results[1] if len(results) > 1 else None
    social = results[2] if len(results) > 2 else None

    if quant is None:
        quant = {
            "asset": ticker,
            "trend": "neutral",
            "indicators": {},
            "levels": {},
            "summary": "量化分析不可用。",
        }
    if news is None:
        news = {
            "asset": ticker,
            "bias": "neutral",
            "key_points": ["新闻分析不可用。"],
            "sources": [],
        }
    if social is None:
        social = {
            "asset": ticker,
            "sentiment": "neutral",
            "signal_available": False,
            "coverage_status": "unavailable",
            "summary": "X 社交分析不可用。",
            "posts": [],
        }

    if on_progress is not None:
        await on_progress("cio", "running", "🧠 CIO 综合研判中…")
    verdict = await cio_agent(llm, ticker, query, quant, news, social)
    if on_progress is not None:
        await on_progress("cio", "done", "✅ CIO 综合研判完成")

    return {
        "asset": ticker,
        "query": query,
        "quant": quant,
        "news": news,
        "social": social,
        "verdict": verdict,
    }
