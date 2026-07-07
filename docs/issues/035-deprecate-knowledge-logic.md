# Issue 035：废弃旧逻辑 —— `generate_knowledge` + `is_knowledge`

**关联 ADR**：[ADR-0017](../adr/0017-unified-section-split.md)（决策3/6）

---

## What to build

section 模式统一后，知识和题目均以 `单元N/` 形式存在，不再需要独立的知识提取和程序侧的类型判定。

### 1. 废弃 `generate_knowledge`

- `default_generate_knowledge`：保留函数体，加 deprecation 日志警告
- `BaseSubjectApp.generate_knowledge()`：section 模式下直接 return（no-op）
- `ui/default_app.py`（L993）：section 模式下跳过 `generate_knowledge` 调用

### 2. 去掉 `is_knowledge` 程序分支

ReAct 模式下 LLM 通过 agent_prompt 第 0 步自行判定内容类型，`is_knowledge` 早已被架空。统一为 `单元N/` 后，`知识/` 目录不再存在，`is_knowledge` 永远为 False。

- `BaseSubjectApp.proofread_one()`：移除 `is_knowledge` 参数
- `default_proofread_one()`：移除 `is_knowledge` 参数
- `ui/default_app.py`：移除 `is_knowledge = (q_name == "知识")` 判断逻辑
- 保留 `knowledge_prompt_lines` 字段在 config 中（向后兼容），但不再使用

### 3. 学科 split_lecture 简化

各学科 `split_lecture` 中移除 `generate_knowledge` 调用和 `strip_decor_images` 调用（已提升到 defaults.py），简化为直接委托 `default_split_lecture`。

## Acceptance criteria

- [ ] 拆分后无 `知识/` 目录生成
- [ ] `proofread_one` 正常调用（无 `is_knowledge` 参数错误）
- [ ] `default_proofread_one` 签名正确
- [ ] UI 校对流程不依赖 `is_knowledge`
- [ ] 各学科 `split_lecture` 代码量减少（移除重复调用）
- [ ] `generate_knowledge` 调用时输出 deprecation 日志
- [ ] 单元测试覆盖：无 `is_knowledge` 的校对流程

## Blocked by

- Issue 034（规则拆分统一完成后才能验证废弃逻辑）
