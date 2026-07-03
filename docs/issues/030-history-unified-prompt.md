# Issue 030：历史 agent_prompt 新建（按统一三段式架构）

## Parent

ADR-0015（统一校对流程）— P2 历史

## What to build

高中历史目前**没有 agent_prompt.json**（ReAct 模式直接用 question_prompt_lines）。新建 `agent_prompt.json`，直接按"预处理→todolist→三阶段主校对"架构编写。

**历史特有维度**：
- 内容类型判据：含"根据材料……""结合所学……"等设问 → 题；年代/事件/因果归纳 → 知识
- 通用检查：标点、编号、错字、历史术语规范
- 题目专项：史料分析逻辑、设问与答案匹配度
- 知识专项：年代准确性、事件因果链条、人名地名正确性
- 混合匹配：史料是否支撑题目设问、知识点是否覆盖题目考察

## Acceptance criteria

- [ ] agent_prompt.json 存在，符合三段式架构
- [ ] 历史学科特有判据正确区分题/知识/混合
- [ ] 纯题目、纯知识、混合三种场景均能正确走对应流程
- [ ] 非 ReAct 模式不受影响

## Blocked by

Issue 026（删除知识分割模式）
