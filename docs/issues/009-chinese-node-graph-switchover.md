# 009: 高中语文节点图 prompt 上线切换

## Parent

ADR-0008（语文校对节点图重构）

## What to build

AB 对比验证通过后，将节点图 prompt 切换为默认，保留旧 prompt 作 fallback。

- 将当前 `agent_prompt.json` 备份为 `agent_prompt_v3.0_backup.json`（若 Issue 007 已做备份则跳过）
- 确认新 prompt 已写入 `agent_prompt.json`
- 确认 `react_mode` 切换正常工作（开/关分别走新/旧 prompt）
- 确认非 ReAct 模式不受影响（`question_prompt_lines` 未改动）
- 更新 `subject.py` 如有需要（本次无需改动，但需确认）

## Acceptance criteria

- [ ] `agent_prompt.json` 为节点图新 prompt
- [ ] `agent_prompt_v3.0_backup.json` 为旧 prompt
- [ ] react_mode=True → 走节点图 prompt（8 分支 todolist）
- [ ] react_mode=False → 走 `question_prompt_lines`（行为不变）
- [ ] 非 ReAct 模式完整流程正常（转换 → 拆分 → 校对 → PDF）
- [ ] 至少跑通 1 题全流程验证

## Blocked by

- #008（AB 对比验证通过）
