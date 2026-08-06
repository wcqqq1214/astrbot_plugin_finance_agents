# Finance Agents

AstrBot 多智能体金融分析插件。对一个标的并行运行三个研究智能体（量化技术面 / 宏观新闻情绪 / X 社交情绪），再由 CIO 智能体折叠多空论据、给出综合研判。

数据来自 yfinance（行情指标）与 Tavily（新闻、X 帖子）。Tavily 复用 AstrBot 内置 web search 已配置的 key，无需额外配置。

> 数据仅用于信息参考，不构成任何投资建议。

## 使用

```
/analyze AAPL 我该现在买入吗？
/analyze AAPL
/help
```

`/analyze` 会立即回复一条"开始分析"消息，随后在后台异步推送各智能体的进度，最终输出完整研判报告（纯文本）。全程约 1-2 分钟。

### 输出结构

- 综合结论：CIO 调和多空后的最终研判
- 最强多头论据 / 最强空头论据
- 各智能体摘要：量化技术面、新闻情绪、X 社交情绪
- 数据来源：新闻与 X 帖子的原始链接

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `news_days` | 7 | 新闻检索回溯天数 |
| `x_search_enabled` | true | 是否抓取 X 帖子 |
| `x_search_days` | 7 | X 检索回溯天数（服务端过滤不可靠，实际以 LLM 端时间判断兜底） |
| `max_results` | 8 | 每路检索的最大结果数 |
| `agent_timeout` | 90 | 单个智能体超时（秒） |
| `show_sources` | true | 最终报告中是否附带来源链接 |

## 架构

```
/analyze AAPL
   └─ run_analysis（原生 asyncio，无 langgraph）
        ├─ asyncio.gather 并行三路
        │    ├─ Quant Agent   —— yfinance 取指标 → LLM 判定 trend/levels/summary
        │    ├─ News Agent    —— Tavily news → LLM 判定 bias/key_points
        │    └─ Social Agent  —— Tavily x.com → LLM 判定 sentiment/signal_available
        └─ CIO Agent（单次调用，2a 折叠）
             ├─ 先构造 bull_case / bear_case
             └─ 再调和为 final_decision
```

要点：

- **确定性取数 + 单次 LLM 总结**：三个研究智能体都先取真实数据，再让 LLM 做一次结构化总结（输出严格 JSON），没有 tool-calling 循环，稳定且延迟可控。
- **技术指标**：SMA20、MACD(12,26,9)、布林带(20,2)、区间涨跌幅，全部在 `tools/market.py` 里用 pandas 计算。
- **X 抓取**：`include_domains=["x.com"]` 直调 Tavily。Tavily 的 `start_date` 对 X 检索不可靠，因此社交智能体的提示词要求只采信近 7 天帖子（帖子文本内嵌时间戳），并有 `signal_available` / `coverage_status` 兜底规则。
- **容错**：单路失败/超时不影响整体，CIO 会拿到标记"不可用"的子报告并据此调整判断；LLM 输出解析失败时有确定性兜底。

## 开发

```bash
uv sync            # 安装依赖
ruff format .      # 格式化
ruff check .       # 静态检查
```

## License

AGPL-3.0-or-later
