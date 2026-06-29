# ADR 0007：物理自主解题 Agent（多轮纠错闭环）

**状态**：仅设计，未实现
**日期**：2026-06-29
**决策者**：MikeTheWiTness
**相关 ADR**：[[ADR 0006 物理校对 ReAct 学科化重构]](0006-physics-react-subject-specialization.md)、[[ADR 0005 ReAct 机制核心架构]](0005-react-mechanism-architecture.md)

---

## 背景

ADR-0006 为物理校对引入了"难题独立解题"能力，但早期用**轻量单次 API** 实现（`independent_solve` 工具内部发起一次无上下文 API 调用）。

问题：即使头部大模型，对**物理过程复杂的大题，单次回复仍有可观错误率**。轻量独立解题继承了单次错误率天花板——极复杂大题单次解可能也错，主 agent 据错误独立解下判断会误判。

但实践观察：通过**多轮交流**，大模型基本都能意识到自己的错误并修正。ADR-0005 的 ReAct 框架已具备多轮纠错的物理基础（对话历史完整保留 + 工具循环），缺的是"自主排查错误 + 验证结果可信度"的编排层——而这里的"错误"指的是**物理解题过程中的错误**（建模、列方程、求解），不是校对动作的错误（后者已在 ADR-0006 的标记前反思中覆盖）。

本 ADR 设计一个完整的**物理自主解题 agent**，把"多轮纠错（解题过程纠错）"固化为结构化、工具驱动的闭环，作为 ADR-0006 `independent_solve` 工具**内部实现**的未来替换方案。本 ADR **仅设计，不实现**。

## 与 ADR-0006 的边界

```
ADR-0006 反思纠错                         ADR-0007 解题纠错（本 ADR）
─────────────────                        ──────────────────────────
范围：校对动作执行是否正确                   范围：物理解题过程是否正确
触发：标记前反思（prompt 内）                触发：verify_result / finalize_result（工具驱动）
纠什么：                                    纠什么：
  ✅ sympy 验算返回 error/异常                 ✅ 物理模型选对了吗？
  ✅ independent_solve 返回结果明显不合理        ✅ 方程列对了吗？（受力/能量/动量）
     （量纲错、超物理边界）                    ✅ 求解步骤对吗？（代数错误、遗漏中间量）
  ✅ 格式检查发现问题                           ✅ 分段衔接对了吗？（前段输出≠后段输入）
  ❌ 不纠物理解题过程（模型/方程/求解）          ✅ 量纲一致、守恒量核对（工具自动）
```

**一句话**：ADR-0006 纠"校对动作"，ADR-0007 纠"解题过程"。本 ADR 通过替换 `independent_solve._run` 内部实现来纠解题过程，校对主流程（ADR-0006）完全不受影响。

## 与 ADR-0006 的关系

```
ADR-0006（校对主流程，已接受）
   固定流程第 6 步：independent_solve 工具
           ├ 早期实现：轻量独立解题（单次 API / 干净上下文）
           └ 未来实现：本 ADR 的 ReAct 自主解题 agent（替换 _run 内部）
                         ↑
                         └── 仅替换解题过程内部实现，不碰校对主流程
   工具签名不变：(question_without_answer, solve_prompt) -> {answer, reasoning, ...}
   校对流程第 6/7 步调用方式不变
   _物理求解.md 结构预留扩展位

边界：ADR-0006 标记前反思 → 纠校对动作（sympy error/量纲异常/格式）
      ADR-0007 verify_result → 纠解题过程（建模/列方程/求解/分段衔接）
```

**关键约束**：本 ADR 的解题 agent 是 `independent_solve` 的**内部实现**，对外仍是一个工具调用。校对主流程（todo list、第5/7步）零改动。本 ADR **仅设计，不实现**。

## 决策

### 决策 1：自主规划 / 自主排查 / 自主验证 三闭环

**选择**：解题 agent 用三个工具调用闭环，把单次解题升级为多轮自我纠错：

```
plan_update（规划做题顺序）
    ↓
┌─→ 求解一步（solve_equation / solve_physics_formula / physics_solve_chain）
│       ↓
│   verify_result（强制验证本步）
│       ├ ok=true  → 进入下一步
│       └ ok=false + issue → 回到本步重解（plan_update 动态插入重解项）
│       ↓
└── 全部步骤 completed
        ↓
   finalize_result（可信度门槛）
       ├ ok=true  → 返回独立答案
       └ ok=false + missing → 回头补齐
```

**核心机制**：
1. **自主规划做题顺序**：`plan_update` 首轮声明多过程分步计划（过程1→过程2→…），每步含"解什么/用什么方程/预期中间量"。物理大题多过程串联，顺序错了一错到底，强制首轮规划；验证失败时动态插入/重排步骤。
2. **自主排查错误**：`verify_result` 每步求解后强制调用，**工具内部做自动化检查**（不靠 LLM 自觉），发现问题以结构化 `issue` 反馈回对话，LLM 必须处理——把"多轮交流才能纠错"的能力固化为工具驱动。
3. **自主验证可信度**：`finalize_result` 是硬门槛，全部满足才返回答案。避免 LLM 调完工具直接下结论。

### 决策 2：编排工具集

| 工具 | 触发时机 | 内部自动检查 | 返回 |
|------|----------|-------------|------|
| `plan_update`（复用 ADR-0005） | 首轮规划 + 验证失败时动态插入/重排 | — | 计划状态 |
| `verify_result` | **每完成一个中间求解步骤后强制调用** | 量纲一致、能量/动量/电荷守恒量、边界合理性、与上环节中间量衔接一致性 | `{ok, issue}` —— `issue` 结构化问题描述，驱动重解 |
| `finalize_result` | 求解+验证循环结束、返回答案前 | 所有步骤 completed？所有 verify 通过？ | `{ok, confidence}` —— 未 ok=true 不返回答案 |

### 决策 3：物理建模工具（建模与求解分离）

**选择**：新增物理建模工具，把"物理建模"从 LLM 自由文本提升为结构化、可落盘的工具调用。

| 工具 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `physics_model_record` | 记录物理模型（受力/运动/能量/电磁场） | 模型结构化描述 | 轻量自洽性校验（方程数≥未知量数、量纲一致、分段连贯）+ 落盘 |
| `physics_solve_chain` | 驱动逐步求解 | 方程组 + 变量链 + 已知量 | 逐步求解结果 + 中间量 + 量纲校验 + 落盘 |

**自洽性校验范围**：只做轻量校验（方程数/量纲/分段），**不判物理模型对错**（超出工具能力）。工具主要价值是①强制 LLM 显式声明模型 ②结构化落盘。物理对错仍靠 LLM + 人类排查 `_物理求解.md` 兜底。

**理由**：现有 6 个 sympy 工具是"数值计算型"，建模过程在 LLM 内部黑箱完成无法保留。建模独立成工具可显式声明、可落盘追溯。复用 `solve_equation`/`solve_physics_formula`/`dimensional_analysis` 实现，不重造计算引擎。

### 决策 4：纠错循环保护——白名单豁免 + 阈值放宽

**选择**：纠错重解会产生短时重复工具结果，必须保护纠错循环不被现有 `empty_streak>=3` 误杀。

- **白名单豁免**：`verify_result`、`finalize_result`、`physics_model_record`、`physics_solve_chain` 加入 `_NAV_CONTROL_TOOLS`，其"重复"结果不计入 `empty_streak`。
- **阈值放宽**：解题 agent 的 `empty_streak` 阈值 3→5，`max_loops` 上调到 40（纠错闭环工具调用多，15-30 轮常态）。

**关键理由**：`_compress_history` 的 summary 语义是"请勿再用工具，凭已有知识判断"（[api_client.py:65-69](../../core/api_client.py#L65-L69)），与纠错闭环目标直接冲突——必须靠白名单让纠错工具豁免，不能让纠错重解被判定为"无效循环"。

**注**：阈值放宽与白名单扩展是解题 agent 的需求。当解题 agent 作为 `independent_solve` 内部实现时，这些参数作用于**解题 agent 自己的 call_api 调用**（独立 messages、独立循环），不影响 ADR-0006 校对主流程的 `call_api`。

### 决策 5：`_物理求解.md` 扩展——多轮求解记录

**选择**：扩展 ADR-0006 的 `_物理求解.md`，增量写入多轮求解记录。

**扩展后内容结构**：
```markdown
# 物理独立求解过程（第N题）

## 物理模型
- 受力分析：...
- 运动过程分段：...

## 所列方程
1. F = ma  → [solve_equation]
2. v² = 2as → [solve_physics_formula]

## 求解与验证过程（多轮）
- 过程1：求解 → verify ok
- 过程2：求解 → verify fail（动能增量>势能减少，违反能量守恒）→ 重解 → verify ok
- 中间量：t=2s, v=8m/s

## 量纲校验
- 全部通过

## 最终独立答案
- 8 m/s（confidence: 高，全步骤 verify 通过 + finalize ok）

## 答案比对
- 题目答案：9.8 m/s
- 独立解：8 m/s → ❌ 不一致
```

**理由**：多轮纠错过程需完整落盘，排查时可定位到"建模/列方程/求解/验证"哪一环出错。结构与 ADR-0006 兼容（ADR-0006 的单次 API 版只填"最终独立答案"段，本 ADR 增量补全其余段）。

## 架构影响（设计，未实现）

### 新增模块

```
shared/physics_solving_agent.py  ← 物理自主解题 agent（替换 independent_solve._run 内部）
   ├─ 解题 agent 的 call_api 调用（独立 messages、独立工具循环、独立阈值）
   ├─ 编排工具：verify_result / finalize_result
   ├─ 建模工具：physics_model_record / physics_solve_chain
   └─ 落盘：增量写 _物理求解.md 多轮记录
```

### 工具归属（与 ADR-0006 切分）

| 工具 | 归属 | 说明 |
|------|------|------|
| 通用 sympy（evaluate/solve_equation/solve_physics_formula/dimensional_analysis/vector/circle） | ADR-0006 主 agent + ADR-0007 解题 agent 共用 | 数值计算，两处都用 |
| `independent_solve` | ADR-0006 | 接口工具，内部实现从单次 API 替换为本 ADR 解题 agent |
| `verify_result` / `finalize_result` / `physics_model_record` / `physics_solve_chain` | ADR-0007 | 编排/建模工具，仅解题 agent 用 |

### 数据流（解题 agent 替换后）

```
ADR-0006 第6步：independent_solve(question_without_answer, solve_prompt)
  │
  └─【ADR-0007 内部实现】解题 agent
        ├─ plan_update：声明多过程分步计划
        ├─ physics_model_record：记录模型 → 落盘 _物理求解.md
        ├─【求解-验证循环】（每个过程）：
        │     solve_* → verify_result
        │       ├ ok=true  → 下一过程
        │       └ ok=false → plan_update 插入重解 → 回到求解（纠错）
        ├─ finalize_result：可信度门槛 → ok=true 才返回
        └─ 返回 {answer, reasoning, confidence} → 落盘 _物理求解.md
              ↓
ADR-0006 第7步：独立答案 vs 题目答案 综合评判（不变）
```

## 后果（预期）

### 正面
- 把"多轮交流才能纠错"固化为工具驱动闭环，直击单次回复错误率高的痛点。
- `verify_result` 结构化反馈 + `finalize_result` 门槛，不依赖 LLM 自觉。
- 作为 `independent_solve` 内部实现替换，校对主流程零改动，风险隔离。
- 多轮求解过程完整落盘，排查可定位到建模/列方程/求解/验证各环。

### 负面
- 解题 agent 工具调用多（15-30 轮），单题耗时与 token 成本大幅增加。
- 新增 4 个工具（verify/finalize/physics_model/physics_solve_chain），解题 agent prompt 变长。
- 实现复杂度高：需独立 call_api 调用 + 独立阈值 + 工具集隔离。

### 风险
- `verify_result` 自动检查只拦**可程序化**错误（量纲/守恒/边界/衔接），拦不住"物理模型选错"这类语义错误——靠 `_物理求解.md` 落盘 + 人类抽查兜底。
- "错得自洽"风险：LLM 建模就错 → 纠错闭环在错误模型上反复重解 → `verify_result` 基于错误模型检查给出 ok=true → `finalize_result` 门槛无法发现。**缓解**：落盘人类抽查；安排"模型选错"类大题回归测试。
- 纠错闭环轮次可能逼近 `max_loops=40`，需观察实际轮次分布，必要时再调。

## 实施时机

**不在当前迭代实施**。触发条件：
1. ADR-0006 轻量独立解题上线后，观察到极复杂大题的单次解题错误率仍是瓶颈（靠 `_物理求解.md` 落盘统计）。
2. 验证 ADR-0006 的 `independent_solve` 接口稳定、校对主流程无回归。

满足后启动本 ADR 的 TDD 落地，仅替换 `independent_solve._run` 内部实现。

## 不纳入

- 解题 agent 跨题复用（每题独立 agent，不共享状态）。
- 解题 agent 的前置搜索（同 ADR-0006，物理无权威原文源）。
- 物理图像/图表自动解析（同 ADR-0006，靠 LLM 多模态）。
- 其他学科的自主解题 agent（待物理验证后再推广）。
