# ADR 0005: ReAct 机制核心架构决议

> 日期：2026-06-27
> 状态：已实现（commit 0241db8；其中 call_api_continue 已于 2026-08-18 删除）
> 关联：CONTEXT.md；参考 Claude Code v2.1.88 源码（`src/query.ts`, `src/tools/TodoWriteTool/`, `src/tools/AgentTool/runAgent.ts`）

## 背景

校对工具从"单次请求→输出"升级为 ReAct Agent 模式。LLM 自主决定工作步骤，系统控制输入（prompt 框架）和输出（格式审查）。

## 决议

### 1. call_api 核心改造

- State vs Config 分离：不可变配置（url, key, model, max_turns）与可变状态（messages, turn_count）分离
- 返回值从三元组扩展为 dict（含 messages 列表 + stop_reason 枚举）
- max_loops 超限：压缩历史 + 去工具（移除无效 tool_calls，插入压缩摘要，下一轮不带 tools）
- 连续 3 轮空/重复结果 → StopReason.TOOL_LOOP
- 新增 `call_api_continue()` 用于格式修正

### 2. PlanUpdateTool（替代自由文本校对计划）

参考 Claude Code `TodoWriteTool`：
- LLM 通过工具调用管理计划状态（非系统解析文本）
- 数据结构：`{content, status: pending|in_progress|completed, activeForm}`
- 恰好 1 项 in_progress；完成即标记；3+ 项才启用
- 全部 completed → 工具返回值追加自查 nudge
- 系统从 tool_calls_log 读取渲染 UI，零解析错误

### 3. 格式审查：二级制

- 第一级：程序检查 —— 段落区域定位 + 编号集合一致性
- 第二级：LLM 格式修正 —— `call_api_continue`（无工具）+ 精简 prompt；仅重组格式

### 4. Prompt 结构

- 新增 `agent_prompt_lines`，与 `question_prompt_lines` 完全独立
- `subject.py` 的 `self.react_mode` 属性切换
- 缺失时 fallback 到旧 prompt
- 工具使用指南详细展开（参考 Claude Code prompt.ts 的密度）

### 5. 前置搜索协调

- ReAct 模式下前置搜索仍执行，结果注入 context 而非替换 prompt
- 不关闭 LLM 的工具调用能力
- 约束行从"严禁"改为"建议"

### 6. max_loops：语文 3→15，物理 20→30

### 7. ReAct 开关：`subject_app.react_mode` 属性传递（方案 A）

### 8. 中间产物：新增 `_校对计划.md` + `_对话历史.json`

## 不纳入

- Phase 2 独立自审轮次（PlanUpdateTool nudge 已覆盖）
- 流式响应
- 其他学科（高中物理除外）

## 后果

### 正面
- LLM 自主规划能力；格式合规率预期提升
- PlanUpdateTool 提供结构化进度跟踪
- 完整对话历史落盘

### 风险
- prompt 长度增加 → 注意力稀释
- `call_api` 改动面大 → 需充分测试
- 高中语文 prompt 变动 → 保留 fallback AB 对比
