# Issue 023：Prompt 获取方法模板化

## Parent

ADR-0011（学科代码重复消除与共享层提取）— prompt 方法重复

## What to build

将 `get_question_prompt`、`get_knowledge_prompt`、`get_review_prompt` 三个方法的公共控制流提取到基类，子类通过少量属性/方法覆盖实现差异化。

**当前状态**：

| 方法 | 模式数 | 差异点 |
|------|--------|--------|
| `get_question_prompt` | 2 种 | 是否追加 `tool_instructions` |
| `get_knowledge_prompt` | 3 种 | 同上 + 是否优先用 `knowledge_agent_prompt_lines` |
| `get_review_prompt` | 3 种 | 同上 + 语文的 ReAct 分支有特殊逻辑 |

**修复方向**：
1. 基类提供统一入口 `_get_prompt(base_key, agent_key, *, knowledge_agent_key=None, append_tool_instructions=None)`：
   - 处理 ReAct / 非ReAct 分支
   - 根据 `append_tool_instructions` 决定是否追加工具指令
   - 接受可选的 `block_type` 参数（本期传 `None`，未来传 `"knowledge"` / `"question"` 用于讲义块分流）
2. 子类通过以下可覆盖属性/方法控制行为：
   - `_append_tool_instructions: bool` — 是否追加工具指令
   - `_has_knowledge_agent: bool` — 是否优先使用 `knowledge_agent_prompt_lines`
   - `_build_review_prompt_react()` — 语文覆盖此方法实现特殊的 ReAct 批注逻辑
3. `get_knowledge_prompt` 的 `knowledge_agent` 回退逻辑：基类提供默认（无回退），物理/化学覆盖为 `True`

## Acceptance criteria

- [ ] 基类实现 `_get_prompt` 统一骨架，三个 prompt 方法委托给它
- [ ] 工具指令追加行为由 `_append_tool_instructions` 属性控制，不再每科重复 if 分支
- [ ] 物理/化学的 `knowledge_agent_prompt_lines` 回退逻辑通过 `_has_knowledge_agent = True` 保持
- [ ] 高中语文的 ReAct 批注评审特殊逻辑通过覆盖方法保持
- [ ] 所有 7 个学科的三种 prompt 输出与重构前逐字一致
- [ ] `_get_prompt` 接受 `block_type=None` 参数，为讲义块分流预留扩展点（本期不改变行为）

## Blocked by

Issue 022（`proofread_one` 模板化完成）
