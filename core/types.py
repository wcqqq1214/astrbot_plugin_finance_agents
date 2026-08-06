"""Shared type definitions for the multi-agent finance plugin."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

BiasLabel = Literal["bullish", "bearish", "neutral"]


class QuantReport(TypedDict, total=False):
    asset: str
    trend: BiasLabel
    indicators: dict[str, Any]
    levels: dict[str, Any]
    summary: str


class NewsReport(TypedDict, total=False):
    asset: str
    bias: BiasLabel
    key_points: list[str]
    sources: list[dict[str, Any]]


class SocialReport(TypedDict, total=False):
    asset: str
    sentiment: BiasLabel
    signal_available: bool
    coverage_status: Literal["available", "unavailable"]
    summary: str
    posts: list[dict[str, Any]]


class CIOVerdict(TypedDict):
    asset: str
    bull_case: str
    bear_case: str
    final_decision: str
    final_summary: str


class AnalysisResult(TypedDict):
    asset: str
    query: str
    quant: QuantReport
    news: NewsReport
    social: SocialReport
    verdict: CIOVerdict


class TavilyResult(TypedDict):
    title: str
    url: str
    snippet: str
    source: NotRequired[str]
    published_time: NotRequired[str]
