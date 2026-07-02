# ADR 0012：框架工程债识别与修复路线

**状态**：提议中
**日期**：2026-06-30
**决策者**：MikeTheWiTness
**关联**：[[ADR 0010 Harness/ReAct/Plan Mode 升级]](0010-harness-react-planmode-upgrade.md)、[[ADR 0011 学科代码重复消除]](0011-subject-code-dedup.md)

---

## 背景

ADR-0010 聚焦于设计层面的升级（工具塑形、格式闸门、ReAct 阶段管理）。在 grill 过程中，识别出一批与设计决策无关的框架层面工程问题——它们不影响"校对效果"，但影响系统的可靠性、可维护性和成本可控性。

---

## 发现

### 🔴 1. 全局状态污染（并发 Bug）

```python
# api_client.py:253-254
from shared.text_nav_tools import set_current_text as _set_nav_text
_set_nav_text(md_text)
```

`set_current_text` 是模块级全局单例。`_proofread_thread` 使用 `ThreadPoolExecutor` 并发校对多道题，**所有线程共享同一个 `current_text`**，存在竞态条件。当前并发模式下的校对结果可能因为读到其他题目的文本而返回错误位置。

**修复方向**：改为线程局部存储（`threading.local()`）或将 `current_text` 作为工具实例属性注入。

### 🔴 2. 零 API 用量追踪

每次 API 调用的响应中包含 `usage` 字段（`prompt_tokens`, `completion_tokens`, `total_tokens`），当前完全未读取。导致：

- 无法判断某次校对是否成本异常
- 无法在连续失败时基于成本信号熔断
- 无 per-question / per-session 成本报表

**修复方向**：在 `call_api` 中提取 `usage` 信息，写入日志和中间产物；在 `default_proofread_one` 中汇总本题目总消耗。

### 🔴 3. 错误处理无分层

所有异常统一 `try/except` + `log(msg)`，无类型区分：

- API 超时 vs 格式错误 vs 工具异常 → 同一条路径
- `MAX_RETRY=2` + `time.sleep(2)` → 无指数退避
- 无熔断器 → 连续失败仍逐个重试

Claude Code 参考：`categorizeRetryableAPIError`、`PROMPT_TOO_LONG_ERROR_MESSAGE`、`FallbackTriggeredError`——每类错误有自己的处理路径。

**修复方向**：定义错误类型层级（`ProofreadError` → `APITimeoutError`, `FormatError`, `ToolExecutionError`），按类型决定重试策略和用户提示。

---

### 🟡 4. 参数传递链过长

`api_url` / `api_key` / `model` 从 UI 到实际 API 调用经过 7 层函数传递，每层都要显式声明这三个参数。

**修复方向**：引入 `SessionContext` 数据类封装配置，在顶层注入，下游按需读取。

### 🟡 5. 日志无结构化

`logging_utils.py` 的 `log()` 只是字符串透传，无日志级别、时间戳、模块名。排查问题时只能文本搜索。

**修复方向**：引入标准 `logging` 模块，按级别输出；中间产物日志也应包含时间戳和来源模块。

### 🟡 6. 配置无 Schema 验证

`config.json` 的结构通过手动 `dict.get()` 读取，拼写错误静默失效。不同学科的配置结构无契约保证。

**修复方向**：Pydantic 或 JSON Schema 验证各学科的 `config.json`，启动时校验并给出明确错误提示。

---

### 🟢 7. API Provider 硬编码

`call_api` 硬编码 OpenAI 兼容的 `/chat/completions` 格式和 `Bearer` 认证。切换 API 提供商需改核心代码。

### 🟢 8. 无 Session 持久化

校对中断（崩溃、关机）后，只能靠检查已有 `_校对报告.md` 来跳过已完成题目——无正式的 session 状态文件。

### 🟢 9. 测试架构零散

30+ 测试文件，无 `pytest.ini`、无 CI 配置、无覆盖率要求。测试用 `unittest.TestCase` 和独立脚本混用。

---

## 修复优先级建议

| 序号 | 项目 | 时机 | 理由 |
|------|------|------|------|
| 1 | 全局状态污染 | 立即 | 并发 Bug，影响正确性，修复代价低（改 1 个文件） |
| 2 | API 用量追踪 | 本期 | 与 ADR-0010 的 `call_api` 扩展同步做，改动面重叠 |
| 3 | 错误处理分层 | 本期 | 格式重试需要区分"可重试"和"不可重试"错误，与 ADR-0010 的格式闸门直接关联 |
| 4 | SessionContext 封装 | 下期 | 改动面大，不宜与 ADR-0010 混合 |
| 5 | 日志结构化 | 下期 | 配合中间产物升级 |
| 6 | 配置 Schema 验证 | 下期 | 与 ADR-0011 重构一起做 |
| 7-9 | API Provider / Session / 测试 | 远期 | 需求驱动 |

---

## 与 ADR-0010 的边界

ADR-0010 是**设计升级**（新增能力），本 ADR 是**工程修正**（修复已有缺陷）。

本 ADR 的 1-3 项（全局状态、用量追踪、错误分层）与 ADR-0010 的实现有关联（都涉及 `call_api` 和 `default_proofread_one` 的改动），建议在 ADR-0010 实现时一并处理，但不写在 ADR-0010 的"决策"中——以保持 ADR-0010 纯粹聚焦于设计方向。
