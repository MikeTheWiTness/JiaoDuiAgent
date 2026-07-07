# Issue 033：基础工具 —— `edit_file` + 手动标记统一

**关联 ADR**：[ADR-0016](../adr/0016-tool-generated-proofread-marks.md)、[ADR-0017 决策5](../adr/0017-unified-section-split.md)

---

## What to build

本 issue 构建两个基础能力，供后续 issue 复用：

### 1. `EditFileTool` 工具（`shared/bash_tool.py`）

新增通用文件搜索替换工具，供 LLM 在 ReAct 流程中使用：

- 工具名：`edit_file`
- 参数：`path`（文件路径）、`old_string`（精确匹配文本）、`new_string`（替换文本）
- 行为：在文件中精确查找 `old_string` 并替换为 `new_string`
- 找不到时返回明确错误（含文件行数、上下文提示）
- 替换成功后返回前后几行的预览

### 2. 手动标记统一（`core/manual_split.py`）

合并题目和知识的手动标记为统一格式：

```
旧：###### 题目开始/结束 ######  +  ###### 知识开始/结束 ######
新：###### 单元开始/结束 ######
```

- `split_by_manual_markers()` + `split_by_knowledge_markers()` → `split_by_unit_markers()`
- 提取共用 `parse_unit_markers(text) -> list[dict]` 解析器
- 不区分题目/知识，全部按单元处理
- 移除 `ManualMarkerError` / `KnowledgeMarkerError`，统一为 `UnitMarkerError`

## Acceptance criteria

- [ ] `EditFileTool` 精确替换成功（含前后预览）
- [ ] `EditFileTool` 找不到匹配时报错（含上下文提示）
- [ ] `###### 单元开始/结束 ######` 手动拆分正确
- [ ] `parse_unit_markers()` 可被 manual_split 和 smart_split 共用
- [ ] 标记不配对时抛出 `UnitMarkerError`
- [ ] 单元测试覆盖：替换成功、未找到、空字符串、多出现

## Blocked by

None — 可立即开始。
