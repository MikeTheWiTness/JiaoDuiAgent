# Issue 042：ADR 残留拆除 —— 知识僵尸链 + 周边死代码 + config 瘦身

**关联 ADR**：[ADR-0019](../adr/0019-architecture-review-fixes.md)（决策 11/12/13/16）

---

## What to build

ADR-0017/0018 落地了一半，「知识提取」概念已废弃但仍以必填字段 + 7 份实现 + UI 状态的僵尸形态存在。本 issue 一次性拆除 ~800 行死/半死代码，9 份 config 只留真差异。完成后读代码的人不再需要穿越 5 层确认「这东西死了」。

### 1. 核心僵尸链（知识提取）

- 删 `default_generate_knowledge`（core/defaults.py）及所有 import（base_subject.py、ui/default_app.py）
- 删 `get_knowledge_prompt` 抽象方法及 7 个学科的实现；删 UI 的 `self.knowledge_prompt` 死状态
- 删 `core/base_subject.py:78` 带 `is_knowledge` 的旧 `proofread_one` 签名（被新定义遮蔽的死代码）
- 删 `core/defaults.py` 的 `_has_real_content`（零调用）
- 删 `core/manual_split.py` 的 `split_by_knowledge_markers` 及旧题目/知识标记常量
- 删 UI「提取知识文件夹」死 checkbox（永不显示且无消费方）
- 删 7 个学科 `split_lecture` 里重复的 `strip_decor_images_from_file` 调用（已提升到 default_split_lecture 内部）

### 2. 周边明确死代码

- 删 `core/config_loader_v2.py`（零调用 + 坏默认值）、`core/paths.py`（零调用）
- 删 `ui/widgets.py` 的 `ModeSelector`（零引用，已被 PipelineBar 取代）、`ui/ui_react.py`、`subjects/高中语文v3.0/subject_react.py`（纯注释残留）
- 删 `core/config_loader.py` 零调用 getter（`get_question_prompt`/`get_knowledge_prompt`/`get_agent_prompt`/`get_section_boundary_enabled`）
- 删 `core/api_client.py` 的 `_strip_search_instructions`（与 defaults.py 同逻辑的两个变体之一，零调用）及未使用的 `FormatError`/`ToolExecutionError` 定义评估
- 清理 7 个学科 subject.py 的未使用 import（AST 验证过的 8-12 个/科）

### 3. config 字段彻底删除（决策 12：不留兼容层）

- `core/config_schema.py` 移除 `knowledge_prompt_lines` 必填校验
- 9 份 config.json 删除 `knowledge_prompt_lines`、`knowledge_agent_prompt_lines` 字段

### 4. config 冗余全清

- 删除与 schema 默认值相同的字段：`split_mode`×9、`exam_pattern`×7、空 `section_pattern_extensions`×8
- 删除死字段 `section_boundary`×8（其 getter 全仓零调用）
- 删除初中英语的哑弹 `section_pattern`（恰等于哨兵值被静默忽略）

### 5. 孤儿学科目录

- 删除 `subjects/初中物理v3.0`、`subjects/初中生物v3.0`（仅 config.json，无代码无引用）

## Acceptance criteria

- [ ] 全仓 grep 无 `generate_knowledge`、`get_knowledge_prompt`、`knowledge_prompt_lines`、`is_knowledge`（除 ADR/文档）
- [ ] 决策 2 列出的死文件/死类/死函数全部删除，无残留 import
- [ ] 9 份 config.json 只含与默认值有差异的字段，启动校验通过
- [ ] 7 个学科 subject.py 无未使用 import
- [ ] 两个孤儿学科目录已删除
- [ ] `pytest` 保持全绿

## Blocked by

- Issue 039（测试防线复位 —— 大删除需要全绿安全网）
- Issue 040、041（同文件改动先行落地，避免冲突）
