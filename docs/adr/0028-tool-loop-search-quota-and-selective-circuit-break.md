# ADR 0028：工具循环搜索独立配额 + 选择性熔断

**状态**：已实现（commit faa4d6d，作为 ADR-0021 call_api 重构中保留的既有功能）
**日期**：2026-07-24
**决策者**：MikeTheWiTness
**关联**：[[ADR 0021 call_api 重构]](0021-call-api-refactor-bashtool-safety-test-degradation.md)

---

## 背景

2026-07-24 全面审查发现 `core/api_client.py` 的工具循环中存在 4 项与 main 分支不一致的功能。经确认，这些改动是此前有意添加的优化，在 ADR-0021 call_api 重构中原样保留。本 ADR 将其显式记录为独立决策，避免与"纯优化零功能变更"基调混淆。

---

## 决策

### C1：搜索工具独立配额（不占 loop 计数器）

**`_SEARCH_TOOLS = {"web_search", "web_fetch"}`**、**`_MAX_SEARCH = 5`**：搜索/抓取工具调用不计入 `loop` 计数器，走独立 `search_count` 配额。

**理由**：搜索是信息收集手段，不是校对动作本身。将搜索轮次从 `loop` 中分离，让 LLM 在 `max_loops` 限制内有更多轮次做实际校对（定位、验证、标记），同时用 `_MAX_SEARCH` 独立上限防止无限搜索。

**行为**：
- 纯搜索轮次（`is_pure_search = True`）：`search_count += 1`，`loop` 不自增
- 搜索配额耗尽时：注入用户消息"搜索次数已达上限"，移除搜索工具，保留其他工具
- 非搜索轮次：`loop += 1`，正常计数

### C2：空结果检测豁免搜索工具

搜索工具（`web_search` / `web_fetch`）的返回结果不计入 `empty_streak` 连续空结果检测。`_NAV_CONTROL_TOOLS`（`plan_update` / `locate_paragraph` / `read_section` 等）同样豁免。

**理由**：搜索无结果是正常情况（数据库未收录、网络波动），不应触发熔断。"空结果"应仅针对计算/验证类工具——这些工具的"空/重复"才真正意味着 LLM 在无效循环。

### C3：选择性熔断（仅移除搜索工具）

连续 3 轮空结果触发熔断时，改为 `_compress_history(messages, len(tool_calls_log), disable_all=False)` + 仅移除搜索工具——保留 `read_file` / `write_file` / `plan_update` 等流程控制与文件操作工具。

**理由**：空结果说明搜索/外部信息收集无法推进，但 LLM 可能仍需用已有知识 + 文件工具完成校对。全禁工具（`openai_tools = None`）会让 LLM 在最后一步失去编辑文件的能力，选择性熔断更精确地定位问题工具集。

---

## 影响

### 正面

- LLM 在 `max_loops` 内有更多有效校对轮次（搜索不占 loop）
- 搜索配额独立上限防止 `web_search` 无限循环
- 空结果熔断后 LLM 仍可调用文件工具完成格式修正

### 风险

- 搜索配额 + 选择性熔断改变了 LLM 可用的工具集与对话上下文，与原来"无限搜索直到 loop 耗尽或全禁"的行为不同
- 对 `max_loops` 较小的学科（如 `max_loops=1`），分离搜索配额的影响较小；对 `max_loops=15` 的 ReAct 学科，影响显著

---

## 与既有 ADR 的关系

- **ADR-0021**（call_api 重构）：本 ADR 记录的功能在 ADR-0021 重构中原样保留，非重构引入
- **ADR-0019**（架构审查修复）：C6.3 红线机制中的熔断逻辑与本 ADR 的选择性熔断互补
