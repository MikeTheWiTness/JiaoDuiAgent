# Issue 026：删除知识分割模式 + 合并 split_lecture

## Parent

ADR-0015（统一校对流程）— 决策 3：合并拆分模式

## What to build

预重构：删除 UI 中"知识智能分割"和"知识人工标记"两个下拉选项，各科 `split_lecture` 删除对应的 `knowledge_smart` / `knowledge_manual` 分支。统一使用 `smart` / `manual` / `rule` / `none` 四种分割方式。

**改动面**：
- UI 下拉去掉两个选项，SPLIT_MODE_MAP 去掉对应映射
- 各科 `subject.py` 的 `split_lecture` 删除 `knowledge_*` elif 分支
- `_update_split_mode_desc` 去掉对应描述
- 不影响已有拆分功能——smart 已能处理混合内容

## Acceptance criteria

- [ ] 下拉框只有 4 个选项：普通规则 / 不拆分 / 智能分割 / 人工标记
- [ ] 所有学科的 `split_lecture` 不再有 `knowledge_smart` / `knowledge_manual` 分支
- [ ] 现有拆分流程端到端通过（讲义、试卷均正常拆分）
- [ ] 测试通过，无回归

## Blocked by

None — 可立即开始
