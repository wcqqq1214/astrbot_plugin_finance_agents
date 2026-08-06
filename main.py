"""Finance Agents — multi-agent financial analysis plugin for AstrBot.

A parallel Quant / News / X-social research pipeline (native asyncio) followed
by a single CIO call that folds the three reports into a bull/bear/verdict.
Research data: yfinance for market indicators, Tavily for news and X posts
(reusing the AstrBot-configured Tavily key, so no extra key setup).

Data is for informational purposes only and is not financial advice.
"""

from __future__ import annotations

import asyncio

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr

from .core.formatting import format_final_message
from .core.llm import LLMError
from .core.orchestrator import run_analysis

_HELP_TEXT = (
    "Finance Agents 多智能体金融分析\n"
    "· /analyze <代码> [问题]   并行量化/新闻/X 三路研究，再由 CIO 综合研判\n"
    "例如：/analyze AAPL 我该现在买入吗？\n"
    "加密货币可直接用币种代码：/analyze BTC、/analyze ETH（自动补 -USD/-USDT 锚定，"
    "可用 crypto_name_map 配置映射）\n"
    "\n"
    "数据仅用于信息参考，不构成任何投资建议。"
)


@register(
    "astrbot_plugin_finance_agents",
    "wcqqq1214",
    "并行 Quant/News/Social 研究 + CIO 综合研判的多智能体金融分析",
    "1.0.0",
)
class FinanceAgentsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.config = config if config is not None else AstrBotConfig()
        self._in_flight: dict[str, asyncio.Task] = {}

    @filter.command("help")
    async def _help(self, event: AstrMessageEvent):
        return event.plain_result(_HELP_TEXT)

    @filter.command("analyze")
    async def _analyze(self, event: AstrMessageEvent, args: GreedyStr):
        parts = args.split(maxsplit=1)
        ticker = parts[0].strip() if parts else ""
        question = parts[1].strip() if len(parts) > 1 else ""
        if not ticker:
            yield event.plain_result("用法：/analyze <代码> [问题]，例如 /analyze AAPL")
            return

        umo = event.unified_msg_origin
        in_flight = self._in_flight.get(umo)
        if in_flight is not None and not in_flight.done():
            yield event.plain_result("⏳ 该会话已有分析进行中，请稍候。")
            return

        yield event.plain_result(
            f"🧠 开始对 {ticker} 进行多智能体分析（量化 / 新闻 / X），"
            "通常需要 1-2 分钟，请稍候…"
        )
        task = asyncio.create_task(self._analyze_async(event, umo, ticker, question))
        self._in_flight[umo] = task
        task.add_done_callback(lambda _: self._in_flight.pop(umo, None))

    async def _analyze_async(
        self, event: AstrMessageEvent, umo: str, ticker: str, question: str
    ) -> None:
        async def _push(text: str) -> None:
            try:
                await self.context.send_message(umo, MessageChain().message(text))
            except Exception as exc:  # noqa: BLE001 - never let progress kill the task
                logger.error("agents: progress push to %s failed: %s", umo, exc)

        async def _on_progress(_stage: str, _status: str, message: str) -> None:
            await _push(message)

        query = question or f"分析一下 {ticker} 的短期走势与投资价值"
        try:
            result = await run_analysis(
                self.context,
                umo,
                self.config,
                ticker,
                query,
                on_progress=_on_progress,
            )
        except LLMError as exc:
            await _push(f"⚠️ 分析失败：{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.error("agents: analysis failed: %s", exc, exc_info=True)
            await _push(f"⚠️ 分析异常：{type(exc).__name__}")
            return

        show_sources = bool(self.config.get("show_sources", True))
        await _push(format_final_message(result, show_sources=show_sources))
