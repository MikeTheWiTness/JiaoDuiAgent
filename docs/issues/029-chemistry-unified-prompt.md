# Issue 029：化学 agent_prompt 重写 + 废弃 knowledge_agent_prompt_lines

## Parent

ADR-0015（统一校对流程）— P1 化学

## What to build

将高中化学 `agent_prompt.json` 和 `knowledge_agent_prompt_lines`（ADR-0014）合并为统一的"预处理→todolist→三阶段主校对"架构。

**关键差异**：
- 内容类型判据：化学特有——方程式+计算要求、实验步骤+反应归纳
- 知识专项维度：配平规则、反应条件、化学计量
- 题目专项：方程验证、化学计量计算（balance/stoichiometry 工具）
- `knowledge_agent_prompt_lines` 废弃——知识校对逻辑合并入统一 agent_prompt
- `get_knowledge_prompt()` 的 ReAct 模式改为直接返回 agent_prompt（不再有 knowledge_agent 回退）
- `config.json` 保留 `knowledge_agent_prompt_lines` 字段但标记为废弃

## Acceptance criteria

- [ ] agent_prompt 为统一三段式，覆盖题目+知识+混合
- [ ] 纯知识校对：行为与当前 knowledge_agent_prompt 一致或更优
- [ ] 混合内容（反应讲解+练习）：走通用→知识→题目→匹配度
- [ ] `get_knowledge_prompt()` 在 ReAct 下返回 agent_prompt
- [ ] 化学计算工具（balance/stoichiometry）不受影响

## Blocked by

Issue 026（删除知识分割模式）
