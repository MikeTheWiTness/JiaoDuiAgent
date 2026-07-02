# Issue 022：`proofread_one` 模板化 + `block_type` 参数预留

## Parent

ADR-0011（学科代码重复消除与共享层提取）— `proofread_one` 模板化

## What to build

将 `proofread_one` 方法提取到基类，6 个学科完全一致，仅高中语文需要额外注入 `pre_hook`（文言文前置搜索）。同时为讲义块拆分预留 `block_type` 参数。

**当前状态**：
- 6 科：选择 prompt → 调用 `default_proofread_one(prompt, tools, max_loops, generate_pdf, react_mode)`
- 高中语文：同上 + 构建 `pre_hook` 闭包传入

**修复方向**：
1. 基类实现 `proofread_one`：选择 prompt → 调用 `self._build_pre_hook(...)` → 调用 `default_proofread_one`
2. `is_knowledge: bool` → `block_type: str = "question"`（可选值 `"question"` / `"knowledge"` / `"lecture"`），为讲义块分流预留接口（本期不改行为，仅改参数名）
3. 新增可覆盖方法 `_build_pre_hook(api_url, api_key, model, q_dir) -> callable | None`，默认返回 `None`
4. 高中语文覆盖 `_build_pre_hook` 返回文言文搜索闭包，其余 6 科无需改动

## Acceptance criteria

- [ ] 基类实现 `proofread_one`，行为与当前 7 份拷贝完全一致
- [ ] `is_knowledge` 重命名为 `block_type`，向后兼容（默认值保持现有逻辑）
- [ ] `_build_pre_hook` 注入点可用，高中语文通过覆盖此方法实现前置搜索
- [ ] 所有 7 个学科的校对流程端到端通过：题目校对、知识校对、批注评审均正常
- [ ] 高中语文的文言文前置搜索 + diff 功能不受影响

## Blocked by

Issue 021（基类 `_write_problems_to_dirs` 提取完成）
