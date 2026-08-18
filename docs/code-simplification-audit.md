# 代码精简审查记录

- 审查日期：2026-08-18
- 审查范围：`main.py`、`core/`、`tools/`、配置与文档、相关 Git 历史
- 审查方式：静态调用链检索、历史变更核验、Ruff 检查
- 代码改动：无

## 结论摘要

当前实现不需要大规模重构。四路研究信号、单路失败隔离、进度推送和信号可用性判定均是已声明的产品边界，不应为减少代码而删除。

发现四组可精简项，其中前两项具有最高收益和最低风险：一组是切换到 Binance 后遗留的行情回退表面积，另一组是 LLM 被要求生成但程序从不消费的 JSON 字段。

## 验证结果

- `uv run ruff check .`：通过。
- `git diff --check`：通过。
- 审查结束时工作树无未提交改动。
- 仓库未跟踪自动化测试、fixture、example 或测试脚本；实施以下变更时应补充针对关键行为的小型回归测试。

## 建议一：移除旧行情回退机制的遗留表面积

**优先级：高**  
**置信度：高**

### 位置

- `core/tickers.py:36,76,82`：`TickerSpec.candidates` 字段及两处赋值。
- `tools/market.py:176-188`：`fetch_first_available()`。
- `tools/market.py:226`：`fetch_first_available([symbol])` 的唯一调用点。
- `core/tickers.py:3-6`：仍描述加密货币使用 yfinance `-USD` / `-USDT` 回退的过时说明。

### 证据

`TickerSpec.candidates` 在仓库内没有读取者。`fetch_first_available()` 仅被股票行情路径调用一次，且调用方永远传入单元素列表 `[symbol]`，因此循环、候选集和聚合错误逻辑均不会提供实际回退能力。

Git 历史显示，这两处在 `772ecb7` 中为加密货币 yfinance `-USD -> -USDT` 回退而引入；加密行情在 `6d3dab5` 改为 Binance 单一 `USDT` 路径后，该表面积不再承载功能。

### 提议

1. 从 `TickerSpec` 删除 `candidates`，并删除两个构造位置的赋值。
2. 删除 `fetch_first_available()`。
3. 在 `fetch_stock_indicators()` 中直接调用 `fetch_indicators(symbol)`。
4. 将 `core/tickers.py` 的模块说明改为当前实际行为：加密行情由 Binance `BASEUSDT` 获取，新闻和 X 搜索仍使用币种全名。

### 取舍与验收

成功取数路径不变。失败时的错误文本将从候选集汇总信息变为原始单标的错误信息；这是更准确的描述。验收时应覆盖股票成功、股票失败和加密货币识别三条路径。

## 建议二：让 LLM 输出契约与真实报告结构一致

**优先级：高**  
**置信度：高**

### 位置

- `core/prompts.py:43-45`：新闻 Agent 被要求输出 `prediction_insights`。
- `core/prompts.py:74-75`：社交 Agent 被要求输出 `keywords`。
- `core/orchestrator.py:171-188`：新闻 Agent 仅解析 `bias` 和 `key_points`。
- `core/orchestrator.py:218-242`：社交 Agent 仅解析 `sentiment`、`signal_available` 和 `summary`。
- `core/types.py:18-31`：`NewsReport` 与 `SocialReport` 均未声明上述两个字段。

### 证据

全仓精确搜索表明，`prediction_insights` 与 `keywords` 只存在于 prompt 指令中，不进入 TypedDict、CIO 输入、最终消息、测试或文档。两个字段自初始实现 `5131a8c` 起没有被接线。

### 提议

从新闻和社交 prompt 的 `exactly these keys` 列表中删除：

- 新闻 Agent 的 `prediction_insights`；
- 社交 Agent 的 `keywords`。

不需要修改报告类型、CIO 输入或用户可见输出。

### 取舍与验收

这两个字段可能被模型作为隐式分析支架使用，但没有直接的程序价值。实施前后应使用若干代表性新闻与 X 帖子样本对比 `bias`、`key_points`、`signal_available` 和 `summary` 的质量与 JSON 解析成功率。

## 建议三：删除完全无消费者的辅助定义

**优先级：中**  
**置信度：高**

### 位置与证据

- `core/parsing.py:59-64`：`safe_float()` 在全仓只有定义，没有调用。
- `core/types.py:62-67`：`TavilyResult` 只有定义，没有运行时、测试或文档消费者。

两者均在初始提交 `5131a8c` 中引入，之后从未接入。

### 提议

删除 `safe_float()` 和 `TavilyResult`。删除 `TavilyResult` 后，同时移除 `core/types.py` 中不再使用的 `NotRequired` import。

### 取舍与验收

这是纯死代码清理，不改变当前运行时行为。验收标准为静态检查通过并确认没有导入错误。

## 建议四：收缩内部结果对象的无消费者字段

**优先级：低**  
**置信度：中**

### 位置

- `core/types.py:44-50`：`CIOVerdict.asset`。
- `core/orchestrator.py:324`：写入 `CIOVerdict.asset`。
- `core/types.py:52-59`：`AnalysisResult.query`。
- `core/orchestrator.py:513`：写入 `AnalysisResult.query`。

### 证据

`core/formatting.py:168-196` 只读取 verdict 的 `bull_case`、`bear_case`、`final_decision` 与 `final_summary`。`AnalysisResult.query` 在构造后没有仓库内读取者；资产名已经由 `AnalysisResult.asset` 在 `core/formatting.py:160` 使用。

### 提议

若 `run_analysis()` 不打算作为供第三方直接调用的稳定 API，可删除 `CIOVerdict.asset`、`AnalysisResult.query` 及对应返回值。

### 取舍与验收

删减幅度有限，并可能影响未文档化的外部调用者，因此应排在前三项之后。验收时应确认最终消息的资产标题、CIO 结论和报告渲染保持不变。

## 明确不建议精简的区域

### 四路研究、故障隔离与 fallback

`core/orchestrator.py:357-503` 中的单路超时、异常捕获、并行执行和不可用报告补齐，保证一条信号失败不会阻止 CIO 输出。这是 README 明确承诺的行为，不应折叠成简单的同步或全有全无流程。

### 信号可用性状态

`signal_available` 与 `coverage_status` 由 `core/orchestrator.py`、`core/formatting.py` 和 `core/prompts.py` 共同使用，用于避免把缺失或稀疏的 X / Polymarket 信号误判为中性信号。它们是近期异常响应加固的一部分，不应删除。

### 条件式任务创建

加密货币限定 Polymarket、Tavily Key 限定新闻与 X、X 开关和相应的跳过进度消息，都是公开配置与用户流程的一部分。将它们改成通用任务表会降低可读性，净简化收益不足。

### CIO 输入中的解释性冗余

`core/formatting.py:88-122` 的 social / prediction `interpretation` 文本与 CIO 系统提示存在一定重复，但其作用是增强 LLM 对不可用信号的服从。当前不建议为少量行数删除该防御性提示。

## 非简化类观察

以下问题不属于代码精简项，单独记录以避免混入本次改动：

1. `metadata.yaml` 仍以三路 Quant / News / X 描述插件，未反映 Polymarket、Binance 与 Twelve Data 的当前实现。
2. `x_search_days` 是配置项并传递给 Tavily 请求，但 `core/prompts.py` 的 social prompt 固定要求审查最近 7 天帖子；非 7 天配置不会完整贯穿 LLM 的可信度判断。

## 推荐实施顺序

1. 先实施“旧行情回退遗留物”和“LLM 未消费字段”两项。
2. 为这两项补充最小回归覆盖后，实施死代码定义清理。
3. 最后再决定是否收缩 `AnalysisResult` 与 `CIOVerdict` 的未消费字段，以免影响任何未文档化的外部调用者。
