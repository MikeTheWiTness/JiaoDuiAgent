# CONTEXT.md — 校对工具 ReAct 机制设计上下文

> 最后更新：2026-06-27
> 状态：设计阶段（grill 完成，issue 已拆分，PRD 已发布；参考 Claude Code v2.1.88 源码深化）

## 1. 问题与目标

### 1.1 当前问题

校对流程是"单次请求→输出"模式：LLM 在一次对话中完成所有工具调用和校对输出。问题：

- LLM 无法**自主规划工作步骤**。被 prompt 强制按固定顺序执行，无法根据题目实际情况调整。
- **没有回溯机制**。LLM 发现前步判断有误后无法回头修正。
- **没有格式自检**。标记和原因数量不匹配、缺少必需段落等格式问题全靠 LLM 自觉。

### 1.2 目标

Agent 自主规划工作步骤，系统只控制入口（prompt 框架）和出口（格式审查）。LLM 在 while-True 工具循环中自主决定：搜索什么、何时标记、何时自查。

---

## 2. 参考架构：Claude Code v2.1.88

从源码（`src/` 目录，TypeScript）提取了以下已生产验证的架构模式：

### 2.1 核心循环：`query()` async generator

**源码**：`src/query.ts`
- `query()` 是一个 async generator，yield 事件流（`StreamEvent | Message | TombstoneMessage`）
- 内部 `queryLoop()` 是 while-True 循环
- `State` 结构体承载跨迭代可变状态（messages, turnCount, transition）
- `QueryConfig` 承载不可变配置（sessionId, gates）—— 与可变 State 分离

**启示**：我们的 `call_api` 不需要变成 generator，但**State vs Config 分离**值得借鉴。当前 `call_api` 的参数和状态混在一起。

### 2.2 TombstoneMessage：压缩历史的正式化

**源码**：`src/types/message.ts`（TombstoneMessage 类型定义）
- 当工具结果过多或上下文超限时，不是丢弃 messages，而是插入 `TombstoneMessage`
- Tombstone 标记哪些 tool result 已被摘要替代
- 配合 `reactiveCompact` 和 `autoCompact` 模块自动触发

**启示**：这就是我们的"压缩历史 + 去工具"的正式化版本。我们不引入完整的 Tombstone 类型，但保留其语义：压缩时插入一条 user 消息代替被删除的 tool_calls。

### 2.3 TodoWriteTool：TODO 列表是工具，不是 UI

**源码**：`src/tools/TodoWriteTool/TodoWriteTool.ts` + `prompt.ts`
- LLM 通过工具调用管理自己的 TODO 列表（不是系统解析文本）
- 数据结构：`{content: "通读全文", status: "pending"|"in_progress"|"completed", activeForm: "正在通读…"}`
- 关键规则：恰好 1 项 in_progress，完成即标记，3+ 项任务才启用
- **Verification Nudge**：全部完成 + 3+ 项 + 无 verification 步骤 → 工具返回值追加提示

**启示（核心）**：我们的 `## 校对计划` 不应该是 LLM 首轮输出的自由文本。应该改为 **`PlanUpdateTool`**：LLM 用工具声明步骤、标记进度。系统从 tool_calls_log 直接读 JSON 渲染 UI 进度。全部 completed 时自动追加自查 nudge。

### 2.4 Agent 循环 `runAgent.ts`

**源码**：`src/tools/AgentTool/runAgent.ts`
- 子 agent 有独立的 `query()` 调用（独立的 while-True 循环、独立 tool set、独立 max_turns）
- `loopDetection` 机制检测工具调用死循环
- `convertToApiMessages` 标准化 messages 格式后发给 API

**启示**：当前单层 agent 够用。未来跨学科校审可参考子 agent 模式。`loopDetection` 优于我们的"连续 3 轮空结果"试探法。

### 2.5 系统 prompt 组织

**源码**：`src/constants/prompts.ts`
- 单一 `DEFAULT_AGENT_PROMPT` 常量，2000+ 行
- 通过 `feature()` 条件控制哪些段落在运行时生效
- 工具使用指南在 prompt 中详细展开（每个工具 200+ 行使用说明）

**启示**：我们的 `agent_prompt_lines` 可以用条件拼接而非两个完全独立的 prompt。工具使用指南应该给出"何时用/何时不用"的上下文，而非罗列工具名。

---

## 3. 组件设计

### 3.1 call_api 核心改造

基于 Claude Code 参考，改造方向：

1. **State vs Config 分离**：`CallApiConfig`（url, key, model, max_turns）为不可变配置；`CallApiState`（messages, turn_count）为跨迭代可变状态
2. **max_loops 超限**：不再清空历史。触发时压缩历史 + 去工具：移除无效 tool_calls/tool_result 对 → 插入压缩摘要 user 消息 → 下一轮不带 tools
3. **返回值扩展**：从 `(content, tool_calls_log, reasoning)` 扩展为 dict，包含 `messages` 列表和 `stop_reason`（end_turn / tool_loop / max_turns / error）
4. **连续空结果检测**：连续 3 轮空/重复结果 → StopReason.TOOL_LOOP → 触发压缩
5. **新增 `call_api_continue()`**：接收已有 messages + 追加消息，发起单次请求（无工具循环），用于格式修正

### 3.2 PlanUpdateTool（替代 ## 校对计划自由文本）

**核心设计**：

```python
class PlanItem(BaseModel):
    content: str      # "通读全文，识别文本类型"
    status: Literal["pending", "in_progress", "completed"]
    activeForm: str   # "正在通读全文…"

class PlanUpdateParams(BaseModel):
    todos: list[PlanItem]

class PlanUpdateTool(BaseTool):
    name = "plan_update"
    description = "更新校对计划的状态。开始新步骤前标记上一项为 completed，新项为 in_progress。恰好 1 项 in_progress。"

    def _run(self, todos):
        # 全部 completed 时追加自查 nudge
        all_done = all(t.status == "completed" for t in todos)
        nudge = ""
        if all_done and len(todos) >= 3:
            nudge = "

所有步骤已完成。在输出最终结果前，请自检：标记数量是否等于修改原因数量？格式是否合规？"
        return {"ok": True, "nudge": nudge}
```

LLM 首轮调用 `plan_update` 声明计划步骤，后续每完成一步调用它更新状态。系统从 tool_calls_log 读取进度渲染 UI，无需解析自由文本。

### 3.3 格式审查（二级制）

**第一级：程序检查**（`_enforce_format`）
- 段落区域定位（非全局正则）：在 `### 标记原文` 和 `### 修改原因` 区域内计数
- 编号集合一致性检查（非简单计数对比）
- 标记格式完整性检查（发现 `【` 后缺少 `编号|` 的情况）

**第二级：LLM 格式修正**（`_llm_format_fix`）
- 不合格 → 调用 `call_api_continue`（不带工具）+ 精简格式修正 prompt
- 仅重组格式，不改校对结论
- 修正后仍不合格 → 标记警告，不阻塞

### 3.4 agent_prompt_lines

- 新增 `agent_prompt_lines` 配置字段，与 `question_prompt_lines` 完全独立（方案 A）
- `subject.py` 通过 `self.react_mode` 属性切换（方案 A：属性传递，不污染函数签名）
- 缺失时 fallback 到 `question_prompt_lines`（不报错）
- 工具使用指南在 prompt 中详细展开，包含"何时用/何时不用/示例"

### 3.5 文本导航工具

- `LocateParagraphTool` / `ReadSectionTool`：类属性注入当前题目 md_text（可变上下文对象）
- 不实现 `count_markers`

### 3.6 前置搜索协调

- ReAct 模式下前置搜索仍执行（保留 Playwright 质量优势）
- 搜索结果注入 context 而非替换 prompt
- 不关闭 LLM 的工具调用能力
- 约束行措辞从"严禁"改为"建议"

### 3.7 max_loops 与防无限循环

| 学科 | 旧 max_loops | 新 max_loops |
|------|-------------|-------------|
| 高中语文 | 3 | 15 |
| 高中物理 | 20 | 30 |

防无限循环：连续 3 轮空结果 → 压缩历史 + 去工具（方案优于追加约束消息）

---

## 4. 中间产物

| 文件 | 内容 | 新增/现有 |
|------|------|----------|
| `_校对报告.md` | LLM 最终输出 + 工具调用日志 + 思考过程 | 现有 |
| `_校对数据.json` | 结构化校对解析结果 | 现有 |
| `_校对计划.md` | PlanUpdateTool 的最终状态（所有步骤 + 完成状态） | **新增** |
| `_对话历史.json` | 完整 messages 列表（含 system/user/assistant/tool） | **新增** |

---

## 5. 文件级改动清单

| 优先级 | 文件 | 改动 |
|--------|------|------|
| P0 | `core/api_client.py` | State/Config 分离；返回值扩展；压缩历史机制；StopReason 枚举；`call_api_continue` 新增 |
| P0 | `core/defaults.py` | `_enforce_format` 重写；`_llm_format_fix` 新增；中间产物落盘新增 |
| P0 | `subjects/高中语文v1.1/config.json` | 新增 `agent_prompt_lines` |
| P0 | `shared/plan_tools.py` | **新增**：`PlanUpdateTool` |
| P1 | `subjects/高中语文v1.1/subject.py` | `react_mode` 属性；prompt 切换；max_loops 15；前置搜索协调 |
| P1 | `core/config_loader.py` | 加载 `agent_prompt_lines` |
| P1 | `shared/text_nav_tools.py` | **新增**：`LocateParagraphTool`、`ReadSectionTool` |
| P1 | `shared/chinese_classics_tools.py` | 约束行措辞修改 |
| P1 | `subjects/高中物理v1.8/` | `agent_prompt_lines`；max_loops 30 |
| P2 | `ui/default_app.py` | ReAct 复选框（默认开启） |

---

## 6. 迁移与评估

- 高中语文先试点，保留旧 prompt 作 fallback（AB 对比）
- 评估标准：已知 bug 修复率
  - 批注重复杂校对
  - 输出格式错误（标记/原因数量不匹配）
  - 复杂过程题目判断错误
- 全部完成后推广到物理 → 其他学科按需跟进

---

## 7. 文档结构

```
docs/
├── adr/                              ← 架构决策记录
│   └── 0005-react-mechanism-architecture.md
├── issues/                           ← 拆分后的 issue
│   ├── 001-call-api-preserve-history.md
│   ├── 002-format-enforcement.md
│   ├── 003-agent-prompt-infra.md
│   ├── 004-text-nav-tools-presearch.md
│   └── 005-ui-integration-full-link.md
└── prd/                              ← 产品需求文档
    └── react-mechanism.md
```

## 8. 不纳入范围

- Phase 2 独立自审轮次（PlanUpdateTool 的 nudge 机制已覆盖）
- 流式响应（streaming）
- 其他学科 agent_prompt_lines（高中物理除外）
- 子 Agent 跨学科校审
