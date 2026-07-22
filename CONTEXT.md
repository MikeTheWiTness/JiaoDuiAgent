# CONTEXT.md — 校对工具 ReAct 机制设计上下文

> 最后更新：2026-07-22
> 状态：通用 ReAct 机制已上线；物理校对 ReAct 学科化重构设计完成（ADR-0006，待落地）；物理自主解题 agent 另立 ADR-0007（仅设计）；语文题目校对节点图重构已上线（ADR-0008）；语文知识类校对维度叠加架构设计完成（ADR-0009，待落地）；工具生成校对标记设计完成（ADR-0016，待落地）；统一规则拆分 section 模式设计完成（ADR-0017，待落地）；智能拆分工具化设计完成（ADR-0018，待落地）；架构审查修复设计完成（ADR-0019，待落地）

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
| P0 | `subjects/高中语文v3.0/config.json` | 新增 `agent_prompt_lines` |
| P0 | `shared/plan_tools.py` | **新增**：`PlanUpdateTool` |
| P1 | `subjects/高中语文v3.0/subject.py` | `react_mode` 属性；prompt 切换；max_loops 15；前置搜索协调 |
| P1 | `core/config_loader.py` | 加载 `agent_prompt_lines` |
| P1 | `shared/text_nav_tools.py` | **新增**：`LocateParagraphTool`、`ReadSectionTool` |
| P1 | `shared/chinese_classics_tools.py` | 约束行措辞修改 |
| P1 | `subjects/高中物理v3.0/` | `agent_prompt_lines`；max_loops 30 |
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

## 8. 物理学科化重构（ADR-0006）

通用 ReAct 机制（ADR-0005）以"文本校对"为心智模型，未覆盖物理校对最难的"答案正确性"维度，且缺独立解题手段，导致物理大题准确率低。详见 [ADR-0006](docs/adr/0006-physics-react-subject-specialization.md)。完整 ReAct 自主解题 agent（多轮纠错闭环）另立 [ADR-0007](docs/adr/0007-physics-autonomous-solving-agent.md)，仅设计不实现。

### 8.1 根因

| # | 问题 | 位置 |
|---|------|------|
| 1 | PlanUpdateTool 计划模板是文本校对模板，未覆盖"答案正确性"维度 | [plan_tools.py:84-99](shared/plan_tools.py#L84-L99) |
| 2 | prompt 是"代入验证已有答案"范式，缺乏"独立重算"范式 | [agent_prompt.json:33](subjects/高中物理v3.0/agent_prompt.json#L33) |
| 3 | 缺"独立解题"手段，主 agent 已见答案、判断被污染 | — |

### 8.2 设计原则

**校对是主任务，解题是手段**。计划结构是校对检查项 todolist（错词/格式/解析正确性/…），非解题链路。仅当校对到"解析正确性"且判定为难题时，才触发"独立解题"作为答案校对手段。**独立解题用可替换接口实现**：早期轻量（单次 API），未来 ADR-0007 替换内部实现，主流程零改动。

### 8.3 核心决策（ADR-0006）

1. **校对检查项 todolist + 难题独立解题**：计划模板为校对 todolist，第6步"独立解题"仅难题插入。
2. **PlanUpdateTool 物理专用化**：nudge 聚焦校对完整性（解析是否实算验证、独立答案是否比对、量纲是否校验）；通用工具加 `nudge_template` 注入点，语文 nudge 不变。
3. **`independent_solve` 可替换接口**：主 agent 调用，传入去答案题目+解题 prompt，工具内部新开干净上下文（无主对话历史）发起单次 API 解题，返回独立答案。**签名稳定**，未来 ADR-0007 只替换 `_run` 内部实现。
4. **新增 `_物理求解.md`**：落盘独立解题输入/独立答案/答案比对，排查大题答案判错。
5. **工具循环阈值微调**：物理 `max_loops` 25→30；`independent_solve` 加入 `_NAV_CONTROL_TOOLS` 白名单。激进阈值放宽随 ADR-0007。
6. **prompt 重写**：区分"代入验证"（第5步默认）与"独立解题"（第6步难题），LLM 自判难题（多过程/电磁场/能量动量转化/复杂受力）。
7. **为 ADR-0007 预留接口**：`independent_solve` 签名稳定 + `_物理求解.md` 预留扩展位 + 工具集分层（通用 sympy 留主 agent，编排/建模工具归 ADR-0007）。

### 8.4 物理专用计划模板（校对 todolist）

```
1. 错词错字校对
2. 格式问题校对
3. 公式符号/单位/矢量符号校对
4. 题干严谨性/物理情景描述校对
5. 解析正确性校对（sympy 工具实算验证解析计算）
6.【若难题】剪掉答案与上下文，independent_solve 独立解题
7.【若难题】独立答案 vs 题目答案 综合评判
8. 生成校对报告（标记原文 + 修改原因）
9. 检查报告格式，bash 修改格式
```

### 8.5 物理中间产物

| 文件 | 内容 | 状态 |
|------|------|------|
| `_物理求解.md` | 独立解题输入 + 独立答案 + 答案比对（ADR-0007 扩展为多轮求解记录） | **新增** |

### 8.6 待落地清单（issue 拆分基础）

| 优先级 | 文件 | 改动 |
|--------|------|------|
| P0 | `shared/physics_tools.py` | **新增**：`IndependentSolveTool`（轻量单次 API，内部可替换） |
| P0 | `subjects/高中物理v3.0/agent_prompt.json` | 重写：校对 todolist + 难题独立解题步骤 + 双场景工具规则 |
| P0 | `shared/plan_tools.py` | `nudge_template` 注入点 |
| P1 | `subjects/高中物理v3.0/subject.py` | 接入 independent_solve + max_loops 30 |
| P1 | `core/api_client.py` | `_NAV_CONTROL_TOOLS` 扩展 + independent_solve |
| P1 | `core/defaults.py` | `_物理求解.md` 落盘协调 |
| P2 | 测试 | 校对 todolist E2E（大题/小题各一例）+ independent_solve 单测 + 白名单兼容性 |

---

## 9. 物理自主解题 Agent（ADR-0007，仅设计）

完整 ReAct 自主解题 agent（多轮纠错闭环），作为 ADR-0006 `independent_solve` 工具**内部实现**的未来替换方案。详见 [ADR-0007](docs/adr/0007-physics-autonomous-solving-agent.md)。

### 9.1 动机

轻量独立解题（单次 API）继承单次错误率天花板，极复杂大题单次解可能也错。但多轮交流大模型基本能纠错——用工具调用把纠错固化为结构化闭环。

### 9.2 三闭环

```
plan_update（规划做题顺序）
    ↓
┌─→ 求解一步 → verify_result（强制验证）
│       ├ ok=true  → 下一过程
│       └ ok=false → plan_update 插入重解 → 回到求解（纠错）
└── 全部 completed
    ↓
finalize_result（可信度门槛）→ ok=true 才返回答案
```

- **自主规划**：`plan_update` 多过程分步，验证失败动态插入/重排。
- **自主排查**：`verify_result` 工具内部自动检查（量纲/守恒/边界/衔接），`issue` 硬反馈驱动重解。
- **自主验证**：`finalize_result` 硬门槛。
- **局限**：自动检查只拦可程序化错误，拦不住"物理模型选错"——靠 `_物理求解.md` 落盘 + 人类抽查兜底。

### 9.3 工具归属切分

| 工具 | 归属 |
|------|------|
| 通用 sympy（evaluate/solve_equation/solve_physics_formula/dimensional_analysis/vector/circle） | ADR-0006 主 agent + ADR-0007 解题 agent 共用 |
| `independent_solve` | ADR-0006（接口，内部实现待 ADR-0007 替换） |
| `verify_result`/`finalize_result`/`physics_model_record`/`physics_solve_chain` | ADR-0007（仅解题 agent） |

### 9.4 实施时机

不在当前迭代实施。触发条件：ADR-0006 轻量独立解题上线后，观察到极复杂大题单次解题错误率仍是瓶颈 + `independent_solve` 接口稳定无回归。满足后仅替换 `independent_solve._run` 内部实现。

---

## 10. 语文学科化重构 —— 节点图（ADR-0008）

物理用单线固定流程（ADR-0006），但语文的文本类型决定校对策略——文言文不做错别字识别（通假字≠错字），默写题核心是逐字比对而非内容判断。**单线固定流程在语文场景是错误抽象**。详见 [ADR-0008](docs/adr/0008-chinese-node-graph-proofreading.md)。

### 10.1 节点图架构

```
第 0 步：LLM 识别文本类型（唯一前置判断点）
  │
  ├─ ① 论述类文本阅读（选择题）
  ├─ ② 文学类文本阅读（散文/小说）
  ├─ ③ 实用类文本阅读（新闻/报告/传记）
  ├─ ④ 文言文阅读 — 不做错别字识别，仅做前置参考逐字比对
  ├─ ⑤ 古诗词鉴赏
  ├─ ⑥ 名篇名句默写
  ├─ ⑦ 语言文字运用（成语/病句/修辞/衔接）
  └─ ⑧ 写作题
```

### 10.2 核心设计原则

- **每个分支是独立的小型固定 todolist**：机械检查（标点、题号、格式）在前，主内容校对在后，格式自检 + 输出收尾。
- **`plan_update` 用于进度标记，不做自主规划**：第 1 轮 LLM 声明对应分支的 todolist，后续逐步标记 completed。
- **`nudge_template` 置空**（与物理一致）：自检靠 prompt 固定步骤，`nudge_template` 参数保留以备未来使用。
- **反思仅做格式自检**：bash 能修的直接修，修不了的打回重做。语文无 sympy 可程序化验证工具，不做内容层打回。
- **允许分支切换**：LLM 怀疑类型有误时，先声明理由 + 重新审视原文特征，确认后才切换分支（两阶段确认）。
- **`max_loops` 保持 15**：最长分支 ~8 步，加反思/切换缓冲充足。
- **不需要 `independent_solve`**：语文无客观可计算验证的答案。文言文/诗歌的独立验证已通过 `pre_proofread_hook` 前置参考注入实现。

### 10.3 改动面

仅重写 `agent_prompt.json`（纯 prompt 层改动），`subject.py`、`plan_tools.py`、`api_client.py` 全部不变。保留旧 prompt 作 fallback 方便 AB 对比。

---

## 11. 不纳入范围

- Phase 2 独立自审轮次（PlanUpdateTool 的 nudge 机制已覆盖）
- 流式响应（streaming）
- 子 Agent 跨学科校审
- 物理前置搜索（无类似语文识典古籍的权威原文源）
- 物理图像/图表内容自动解析（受力图/电路图/v-t 图仍靠 LLM 多模态）
- **完整 ReAct 自主解题 agent（多轮纠错闭环）**：另立 ADR-0007，仅设计；ADR-0006 用轻量独立解题 + 可替换接口先行，待验证后实施 ADR-0007
- 其他学科（化学/数学等）的学科化重构——待物理 + 语文验证后再推广

---

## 12. 工具生成校对标记（ADR-0016，设计中）

### 12.1 问题

当前 LLM 在文本输出中手写内联标记 `【N|原文|改为】`：
- Token 浪费（输出中重复大量原文）
- 复制错误（LLM 截断/改写原文导致标记不准确）
- 格式错误（编号遗漏、分隔符缺失），需要二级格式审查兜底

### 12.2 方案

引入专用工具 `add_proofread_mark` / `update_proofread_mark`，让 LLM 通过工具调用生成标记，替代手写方式。

**核心工具**：

```
add_proofread_mark(paragraph, original, occurrence, corrected, reason)
  → 在文件中定位 → 替换原文为【N|原文|改为】→ 追加原因

update_proofread_mark(mark_number, original?, corrected?, reason?)
  → 修改已有标记的内容和原因
```

**定位方式**：`paragraph + original + occurrence` 三要素精确定位。替换模式保证已标记文字被"消费"，后续 occurrence 计数不受影响。

**文件流程**：
```
源文件.md → 复制到 _校对报告.md（原文 + ### 修改原因 空章节）
          → LLM 用工具逐条编辑文件
          → _校对报告.md 即最终报告
```

### 12.3 关键决策

| 决策 | 选择 |
|------|------|
| 校对范式 | 不变，保留 `【N|原文|改为】` 格式 |
| 标记行为 | 替换原文（原文被标记消费） |
| 文件开头 | 纯文本（不加 `### 标记原文` 标题） |
| 原因记录 | 工具自动追加到 `### 修改原因` 章节 |
| JSON 生成 | 从 `tool_calls_log` 提取 |
| 兼容策略 | 新增可选模式，不替换现有流程 |
| 工具集 | read_file + add/update_mark + edit_file + write_file |

### 12.4 待落地

详见 [ADR-0016](docs/adr/0016-tool-generated-proofread-marks.md)。先在语文学科试验，验证通过后逐步推广。

---

## 13. 统一规则拆分 —— section 模式（ADR-0017，设计中）

### 13.1 问题

当前 7 个学科使用 `title` 模式拆分讲义：按题目标记切分为 `第N题/`，题目之间的知识讲解过滤出来放入独立的 `知识/` 文件夹。高中历史独用 `section` 模式：按标题平等切分，输出统一 `板块N/`，不区分知识和题目。

title 模式的问题：知识提取易漏/错归、审核需在题目和知识间跳转、两套命名增加复杂度。

### 13.2 方案

所有学科统一使用 `section` 模式。

**默认 section_pattern**（内置常量）：
```
^#{2,3}\s                    # ## / ### 标题
|\*\*(例|练|变式|真题)\d+\*\*  # **例1**、**练1** 等
|\*\*教师版\*\*               # **教师版**
|必备知识|模型大招|重难点突破   # 通用知识标题
```

**命名统一**：`板块N` / `第N题` → `单元N`

**知识提取废弃**：`generate_knowledge` 不再需要，知识标题被识别为板块边界后自然成为独立单元。

**学科扩展**：`section_pattern_extensions` 字段留空，各学科后续按需追加领域特有词。

### 13.3 关键决策

| 决策 | 选择 |
|------|------|
| 拆分模式 | 全部改为 section |
| 单元命名 | `单元N` |
| 知识提取 | 废弃 `generate_knowledge` |
| 程序分支 | 去掉 `is_knowledge` 参数（ReAct 下 LLM 自判类型，目录名不再决定校对策略） |
| 通用关键词 | `必备知识`、`模型大招`、`重难点突破` |
| 装饰图片清除 | 提升到 `default_split_lecture` 内部统一执行，各学科不再重复调用 |
| 二级例题提取 | 复用 `wrapped_patterns`，从知识板块中剥离 `**例1**`/`**教师版**` 等真正例题为独立单元 |
| 导航区处理 | `.skip_proofread` 标记替代删除目录，保留考情分析等内容但校对自动跳过 |
| 连续标题合并 | `## 模块N` 紧接 `### 必备知识` 无实质内容时自动合并为一个单元，消除空壳单元 |
| 学科扩展 | 留空，后续按需追加 |

### 13.4 待落地

详见 [ADR-0017](docs/adr/0017-unified-section-split.md)。改动面：`defaults.py`、`config_loader.py`、`config_schema.py`、`base_subject.py`、`default_app.py` + 8 个学科 config。

---

## 14. 智能拆分工具化 + 标记统一（ADR-0018，设计中）

### 14.1 问题

`smart_split` 用 `<problem>` 标签，手动拆分用 `###### 题目开始 ######`，两套标记两套解析。且智能拆分 LLM 输出全文浪费 token、常篡改原文。

### 14.2 方案

1. **标记统一**：手动和智能拆分都用 `###### 单元开始/结束 ######`
2. **工具化**：复用 ADR-0016 的 `edit_file`，LLM 在文件中插入标记而非输出全文
3. **解析统一**：`manual_split.py` 和 `smart_split.py` 共用 `parse_unit_markers()`

### 14.3 标记对照

| | 旧 | 新 |
|---|---|---|
| 手动（题目） | `###### 题目开始 ######` | `###### 单元开始 ######` |
| 手动（知识） | `###### 知识开始 ######` | `###### 单元开始 ######` |
| 智能 | `<problem>...</problem>` | `###### 单元开始/结束 ######` |

### 14.4 依赖

ADR-0016（edit_file 工具）+ ADR-0017（单元命名）→ ADR-0018

### 14.5 待落地

详见 [ADR-0018](docs/adr/0018-smart-split-tool-integration.md)。
