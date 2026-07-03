# Issue 032：数学 agent_prompt 重写

## Parent

ADR-0015（统一校对流程）— P2 数学

## What to build

将小学数学 `agent_prompt.json` 重写为"预处理→todolist→三阶段主校对"架构。

**数学特有维度**：
- 内容类型判据：计算题/应用题/选择题 → 题；定义/定理/公式讲解 → 知识
- 通用检查：题号、单位、符号规范
- 题目专项：计算正确性（sympy 验证）、解题步骤逻辑
- 知识专项：定义严谨性、定理条件完整性、示例正确性
- 混合内容：知识讲解后的例题 → 匹配度检查例题是否可用前文定理求解

## Acceptance criteria

- [ ] agent_prompt 为三段式结构
- [ ] 题目和知识两种类型正确区分
- [ ] sympy 计算工具不受影响

## Blocked by

Issue 026（删除知识分割模式）
