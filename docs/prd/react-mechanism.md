# PRD: 校对工具 ReAct 机制

> 日期：2026-06-27
> 关联：CONTEXT.md、ADR-0005

## Problem Statement

校对 LLM 调用是"单次请求→输出"模式，LLM 无法自主规划步骤、无回溯机制、格式违规全靠自觉。高频 bug：批注重复杂校对、格式错误、复杂题目判断不准。

## Solution

升级为 ReAct Agent。LLM 用 PlanUpdateTool 管理计划状态，在 while-True 工具循环中自主决定搜索/验证/标记顺序。系统负责：入口提供 prompt 框架，出口执行格式审查。

## User Stories

1. 作为校对员，我希望 LLM 在开始校对前声明工作计划，并实时更新完成状态
2. 作为校对员，我希望 LLM 在工具搜索失败后能自主换策略
3. 作为校对员，我希望系统自动检查格式合规性（标记 vs 原因数量），不合格时自动修正
4. 作为校对员，我希望保留旧 prompt 作 fallback
5. 作为校对员，我希望前置搜索（识典古籍）的结果让 LLM 知晓但不禁用其搜索能力
6. 作为系统管理员，我希望检测 LLM 的无效搜索行为（连续 3 轮空结果），自动干预
7. 作为排错员，我希望对话历史完整保存（含 messages、tool_calls、reasoning）
8. 作为排错员，我希望校对计划的状态也落盘保存
9. 作为校对员，我希望在 UI 中看到 LLM 的计划执行进度
10. 作为系统管理员，我希望 ReAct 模式有 UI 开关
11. 作为开发者，我希望 ReAct 改动不破坏现有流程
12. 作为物理校对员，我希望 LLM 能自主决定何时需要符号计算验证

## Implementation Decisions

### call_api 改造
- State（messages, turn_count）与 Config（url, key, model, max_turns）分离
- 返回值包含 messages 列表和 StopReason
- 超限时压缩历史 + 去工具（参考 Claude Code TombstoneMessage）
- 连续 3 轮空结果 → StopReason.TOOL_LOOP

### PlanUpdateTool（参考 Claude Code TodoWriteTool）
- LLM 通过工具调用管理计划，非系统解析自由文本
- 状态：pending → in_progress → completed
- 恰好 1 项 in_progress；全部 completed 时追加自查 nudge
- 系统从 tool_calls_log 读 JSON 渲染 UI

### 格式审查
- 一级：程序检查（段落区域定位 + 编号集合一致性）
- 二级：LLM 格式修正（call_api_continue，无工具，仅重组格式）
- 非 ReAct 模式同样生效

### agent_prompt_lines
- 与 question_prompt_lines 独立；subject_app.react_mode 切换
- 工具使用指南详细展开（"何时用/何时不用/示例"）

### 前置搜索
- ReAct 模式仍执行，结果注入 context，不关闭工具
- 约束行改为建议性措辞

### UI
- ReAct 复选框（默认开启），连接 subject_app.react_mode
- 进度面板：从 PlanUpdateTool 调用记录渲染 TODO 列表

## Testing Decisions
- 测试外部行为，不测内部实现
- 模块覆盖：call_api（工具循环）、_enforce_format（格式检查）、config_loader（agent_prompt_lines 加载）
- 格式审查测试用 20 条历史出错输出作测试集

## Out of Scope
- Phase 2 独立自审轮次
- 流式响应
- 其他学科（高中物理除外）的 agent_prompt_lines
- 子 Agent 跨学科校审
