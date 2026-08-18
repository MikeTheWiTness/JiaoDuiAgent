# Issue 049：ProofreadState 状态机预重构 —— 工具循环状态唯一载体

**关联 ADR**：[ADR-0029](../adr/0029-proofread-checkpoint-resume.md)（ProofreadState 状态机节）

---

## What to build

工具循环的全部运行状态目前散落在 `_run_tool_loop` 的 11 个参数和 6 个局部变量里，且循环中途就地突变 `messages`、`openai_tools`、`payload`（压缩历史、移除搜索工具两处）。本 issue 把这些收拢为 `ProofreadState` 一个数据结构，使「快照 = 序列化 state」成为可能，同时偿还 ADR-0021 / CONTEXT.md 2.1 既定的「State vs Config 分离」欠账。

**纯重构，零行为变更**——本 issue 不引入任何快照/续传功能。

### 状态收拢范围

`ProofreadState` 承载：

- `messages`（完整对话历史）
- 循环计数器：`loop`、`search_count`、`empty_streak`、`recent_results`
- 记录器：`tool_calls_log`、`reasonings`、`assistant_turn`
- 突变后状态：`openai_tools`（搜索配额耗尽/压缩后可能已移除工具）、`reasoning_effort`
- 累计用量：`total_usage`

`payload` **不入 state**——纯派生件（ctx + messages + openai_tools 每轮重建），循环内的 `payload["tools"] = ...`、`payload["messages"] = ...` 突变点随之消失。

### 签名收敛

`_run_tool_loop` 从 11 参数收敛为 5 参数：`(ctx, state, tool_instances, chat_url, headers)`。首条 LLM 响应（choice）的注入方式由实现者决定，但不得恢复参数膨胀。

### 测试移植

现有契约测试（`tests/test_api_client.py::TestRunToolLoopRobustness`，8 个用例）断言对象（stop_reason、reasonings、messages、各退出路径日志落盘、429 退避）全在 state 上，机械移植；断言语义不得削弱（AGENTS.md 测试原则）。

## Acceptance criteria

- [ ] 工具循环的全部可变状态收拢进 `ProofreadState`，循环体内不再有跨轮局部变量
- [ ] `payload` 由 state + ctx 每轮派生，循环内无就地突变
- [ ] `_run_tool_loop` 签名收敛，无 11 参数长签名
- [ ] 8 个契约测试全部移植到 state 断言并通过，断言语义不弱于现状
- [ ] 四条退出路径（END_TURN/MAX_TURNS/TOOL_LOOP/INTERRUPTED）行为逐字不变
- [ ] `call_api` 对外 6-key dict 返回结构逐字不变（ADR-0021 冻结约束）
- [ ] 全量 `pytest` 保持全绿

## Blocked by

- None — 可立即开工
