"""Build CIO prompt blocks from agent reports and format the final message."""

from __future__ import annotations

from typing import Any

from .types import AnalysisResult


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def format_quant_block(quant: dict[str, Any]) -> str:
    """Render the quant report as a structured prompt block for the CIO."""

    indicators = _as_dict(quant.get("indicators"))
    levels = _as_dict(quant.get("levels"))
    lines = [
        "[Quantitative technical report]",
        "Quant technical summary:",
        f"- asset: {quant.get('asset', 'UNKNOWN')}",
        f"- trend: {quant.get('trend', 'neutral')}",
        f"- summary: {quant.get('summary') or 'N/A'}",
        (
            f"- support/resistance: support={levels.get('support')}, "
            f"resistance={levels.get('resistance')}"
        ),
        (
            "- indicators: "
            f"last_close={indicators.get('last_close')}, sma_20={indicators.get('sma_20')}, "
            f"macd_line={indicators.get('macd_line')}, macd_signal={indicators.get('macd_signal')}, "
            f"macd_histogram={indicators.get('macd_histogram')}, "
            f"bb_upper={indicators.get('bb_upper')}, bb_lower={indicators.get('bb_lower')}, "
            f"price_change_pct={indicators.get('price_change_pct')}"
        ),
    ]
    return "\n".join(lines)


def format_news_block(news: dict[str, Any]) -> str:
    """Render the news report as a structured prompt block for the CIO."""

    key_points = (
        news.get("key_points", []) if isinstance(news.get("key_points"), list) else []
    )
    sources = news.get("sources", []) if isinstance(news.get("sources"), list) else []
    lines = [
        "News sentiment summary:",
        f"- asset: {news.get('asset', 'UNKNOWN')}",
        f"- bias: {news.get('bias', 'neutral')}",
        f"- source_count: {len(sources)}",
        "",
        "Key news points:",
    ]
    if key_points:
        lines.extend(f"- {point}" for point in key_points[:6])
    else:
        lines.append("- No key points available.")
    if sources:
        lines.extend(["", "Recent source coverage:"])
        for item in sources[:5]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                f"{item.get('source') or 'Unknown source'} | "
                f"{item.get('published_time') or 'Unknown time'} | "
                f"{item.get('title') or 'Untitled'}"
            )
    return "\n".join(lines)


def format_social_block(social: dict[str, Any]) -> str:
    """Render the social report as a structured prompt block for the CIO."""

    coverage_status = social.get("coverage_status")
    signal_available = social.get("signal_available")
    if coverage_status not in ("available", "unavailable"):
        coverage_status = (
            "available" if signal_available is not False else "unavailable"
        )
    interpretation = (
        "Exclude from retail sentiment judgment."
        if coverage_status == "unavailable"
        else "Use only as ancillary context."
    )
    lines = [
        "Social sentiment summary:",
        f"- asset: {social.get('asset', 'UNKNOWN')}",
        f"- sentiment: {social.get('sentiment', 'neutral')}",
        f"- signal_available: {signal_available}",
        f"- coverage_status: {coverage_status}",
        f"- summary: {social.get('summary') or 'N/A'}",
        f"- interpretation: {interpretation}",
    ]
    return "\n".join(lines)


def format_prediction_block(prediction: dict[str, Any]) -> str:
    """Render the prediction-market report as a prompt block for the CIO."""

    coverage_status = prediction.get("coverage_status")
    signal_available = prediction.get("signal_available")
    if coverage_status not in ("available", "unavailable"):
        coverage_status = (
            "available" if signal_available is not False else "unavailable"
        )
    interpretation = (
        "Exclude from directional judgment; treat as missing context."
        if coverage_status == "unavailable"
        else "Use as crowd-priced directional reference; not a precise forecast."
    )
    lines = [
        "Prediction market summary:",
        f"- asset: {prediction.get('asset', 'UNKNOWN')}",
        f"- bias: {prediction.get('bias', 'neutral')}",
        f"- signal_available: {signal_available}",
        f"- coverage_status: {coverage_status}",
        f"- summary: {prediction.get('summary') or 'N/A'}",
        f"- interpretation: {interpretation}",
    ]
    key_points = (
        prediction.get("key_points", [])
        if isinstance(prediction.get("key_points"), list)
        else []
    )
    if key_points:
        lines.extend(["", "Key prediction-market points:"])
        lines.extend(f"- {point}" for point in key_points[:5])
    markets = (
        prediction.get("markets", [])
        if isinstance(prediction.get("markets"), list)
        else []
    )
    if markets:
        lines.extend(["", "High-volume price levels:"])
        for market in markets[:8]:
            if not isinstance(market, dict):
                continue
            prices = market.get("prices")
            price_text = (
                ", ".join(f"{float(p) * 100:.0f}%" for p in prices)
                if isinstance(prices, list)
                else "N/A"
            )
            lines.append(
                "- "
                f"{market.get('question') or 'Untitled'} | "
                f"prob={price_text} | "
                f"vol24=${market.get('volume24hr', 0):,.0f}"
            )
    return "\n".join(lines)


def format_final_message(result: AnalysisResult, *, show_sources: bool = False) -> str:
    """Render the user-facing plain-text summary of the whole analysis."""

    asset = result["asset"]
    verdict = result["verdict"]
    quant = result["quant"]
    news = result["news"]
    social = result["social"]
    prediction = result["prediction"]

    lines = [f"📊 {asset} 多智能体综合研判", "", "【综合结论】"]
    final_decision = (verdict.get("final_decision") or "").strip()
    if final_decision:
        lines.append(final_decision)
    else:
        lines.append("N/A")

    lines.extend(["", "【最强多头论据】", (verdict.get("bull_case") or "N/A").strip()])
    lines.extend(["", "【最强空头论据】", (verdict.get("bear_case") or "N/A").strip()])

    lines.extend(["", "【各智能体摘要】"])
    lines.append(
        f"· 量化技术面：{quant.get('trend', 'neutral')} — "
        f"{quant.get('summary') or 'N/A'}"
    )
    news_bias = news.get("bias", "neutral")
    first_point = (news.get("key_points") or ["N/A"])[0]
    lines.append(f"· 新闻情绪：{news_bias} — {first_point}")
    if social.get("coverage_status") != "unavailable":
        lines.append(
            f"· X 社交情绪：{social.get('sentiment', 'neutral')} — "
            f"{social.get('summary') or 'N/A'}"
        )
    if prediction.get("coverage_status") != "unavailable":
        lines.append(
            f"· 预测市场（Polymarket）：{prediction.get('bias', 'neutral')} — "
            f"{prediction.get('summary') or 'N/A'}"
        )

    final_summary = (verdict.get("final_summary") or "").strip()
    if final_summary:
        lines.extend(["", "【总结】", final_summary])

    if show_sources:
        sources_lines: list[str] = []
        for item in (news.get("sources") or [])[:3]:
            if isinstance(item, dict) and item.get("url"):
                sources_lines.append(
                    f"· 新闻: {item.get('title', '')} {item.get('url')}"
                )
        for item in (social.get("posts") or [])[:3]:
            if isinstance(item, dict) and item.get("url"):
                author = item.get("author")
                via = f"（@{author}）" if author else ""
                sources_lines.append(
                    f"· X（情绪参考·未经核实）: {item.get('title', '')} "
                    f"{item.get('url')}{via}"
                )
        if sources_lines:
            lines.extend(["", "【数据来源】", *sources_lines])

    return "\n".join(lines)
