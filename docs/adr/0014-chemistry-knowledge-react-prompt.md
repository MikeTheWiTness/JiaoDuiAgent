# ADR 0014：高中化学 ReAct 知识校对场景独立 prompt

**状态**：提议中
**日期**：2026-07-02
**决策者**：MikeTheWiTness
**相关 ADR**：[[ADR 0005 ReAct 机制核心架构]](0005-react-mechanism-architecture.md)、[[ADR 0006 物理 ReAct 学科化重构]](0006-physics-react-subject-specialization.md)

---

## 背景

ADR-0005/0006 落地了 ReAct 机制的固定流程模式，高中化学的 `agent_prompt.json` 定义了一个包含 9 步的题目校对工作流。该工作流的核心特征是：**第 5 步判定难题 → 第 6 步独立解题 → 第 7 步综合评判**，这是针对"题目包含答案和解析，需要验证答案正确性"场景设计的。

但在实际使用中，`get_knowledge_prompt()` 和 `get_review_prompt()` 在 `react_mode=True` 时也返回同一个 agent_prompt，导致两种错配：

1. **知识校对（讲义/学案）**：输入是知识点讲解文本，没有题干、答案、解析的三段结构。第 4 步"题干严谨性校对"、第 5 步"难题判定"、第 6-7 步"独立解题+综合评判"全部无意义，浪费 token 且可能让 agent 产生困惑输出。

2. **批注评审**：输入是原文+批注标签，目的是判断批注建议是否正确。题目校对流程完全不适用。化学学科当前无此需求，可暂缓。

## 设计原则

**场景决定流程，工具决定能力**。不同校对场景需要不同的固定步骤，但共享同一套化学计算工具集。`get_knowledge_prompt()` 应返回知识场景专属的 prompt，而非复用题目校对 prompt。

## 决策

### 决策 1：知识校对使用独立的 7 步工作流

在 `config.json` 中新增 `knowledge_agent_prompt_lines`，定义知识校对专属流程。与题目校对 9 步的对比如下：

| 步骤 | 题目校对 (agent_prompt) | 知识校对 (knowledge_agent_prompt) |
|------|--------------------------|--------------------------------------|
| 1 | 错词错字校对 | 错词错字校对（同） |
| 2 | 格式问题校对 | 格式问题校对（同） |
| 3 | 化学用语校对 | 化学用语校对（同） |
| 4 | 题干严谨性校对 | **知识点准确性校对**（改） |
| 5 | 解析验算 + 难题判定 | **计算示例验证**（改，无难题判定） |
| 6 | 独立解题（仅难题） | —（删除） |
| 7 | 综合评判（仅难题） | —（删除） |
| 8 | 输出校对报告 | 输出校对报告（同） |
| 9 | 格式审查 | 格式审查（同） |

**关键差异**：

- **第 4 步改造**：从"检查题干严谨性（已知条件、数据自洽性）"改为"检查知识点准确性（概念定义、反应条件、实验现象描述是否正确）"，强调必要时使用 `web_search` 联网验证。
- **第 5 步改造**：去掉"难题判定"逻辑和 6/7 步的条件分支。讲义中的计算示例只需代入验证，不需要独立解题（无答案可比对）。
- **工具集**：保留全部化学计算工具（`balance_chemical_equation`、`stoichiometry_calc`、`evaluate_expression`、`solve_equation`、`check_equality`、`simplify_expression`）+ `web_search`。移除 `independent_solve`（无适用场景）。

### 决策 2：批注评审暂不在 ReAct 模式下支持

化学学科当前无批注评审需求，`get_review_prompt()` 在 `react_mode=True` 时保留 fallback 到非 ReAct 的 `question_prompt_lines` 行为。等有实际需求时再按 ADR 流程设计专属 prompt。

### 决策 3：先化学后推广

物理和数学存在同样的问题（ReAct 下知识 prompt 复用题目工作流），但先聚焦化学验证方案，确认可行后再同步。

## 影响

- **正面**：知识校对 agent 不再浪费 token 在难题判定和独立解题步骤上，输出更聚焦。
- **风险**：知识校对 prompt 需要经过实际讲义数据验证，步骤设计可能有迭代调整。
- **兼容性**：`get_knowledge_prompt()` 的行为变更——原来 ReAct 下返回 `agent_prompt_lines`，现在返回 `knowledge_agent_prompt_lines`。非 ReAct 模式不变。

## 实现

1. 在 `config.json` 中新增 `knowledge_agent_prompt_lines` 数组
2. 修改 `subject.py` 的 `get_knowledge_prompt()`：ReAct 模式时读取 `knowledge_agent_prompt_lines`
3. 物理/数学的类似修改作为后续 ADR
