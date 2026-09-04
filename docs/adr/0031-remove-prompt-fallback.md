# ADR 0031：移除提示词回退机制（question_prompt_lines）

**状态**：已实现（commit 待补）
**日期**：2026-09-04
**决策者**：MikeTheWiTness
**关联**：[[ADR 0005 ReAct 机制核心架构]](0005-react-mechanism-architecture.md)、[[ADR 0015 统一校对流程]](0015-unified-proofread-flow.md)

---

## 背景

初期设计为提示词提供双源保底：ReAct 模式（`react_mode=True`）用 `agent_prompt.json` 的 `agent_prompt_lines`（新版三段式提示词），`react_mode=False` 回退到 `config.json` 的 `question_prompt_lines`（旧版静态提示词）。UI 提供「ReAct 模式」复选框。

长期运行后该机制暴露出明确问题：

1. **从未被需要**：生产 UI 恒启用 ReAct（`react_mode=True`），回退路径长期未触发；正常安装的学科目录均由 `main.py` 首次运行时复制 `agent_prompt.json`，不存在缺文件场景。
2. **双源不同步已实际引发两轮事故**：
   - 「逐字抄写题目正文」提示词修复只改了 4 个学科的 `agent_prompt.json`，回退路径（config.json 旧提示词）未同步，测试先行发现数学学科 prompt 丢失「总结行」字样（改造时被整行替换，化学/历史/英语因保留顺序行未暴露）；
   - “混合内容核验说明被编号化”→“格式修正轮伪造『保持原样』批注”问题（单元3 事件）的根源之一，是主模型按 config 旧提示词的混合分段模板把核验说明编号写进「修改原因」。
3. **fail-fast 优于静默回退**：回退机制让「提示词缺失」变成静默降级，掩盖配置错误；真触发时直接报错并重新发起校对，链路更清晰。

## 决策

**移除提示词回退机制，`agent_prompt.json` 成为提示词唯一来源。**

1. **`react_mode` 概念整体删除**：`BaseSubjectApp` 移除 `react_mode` 属性/property；7 个学科 `subject.py` 删除全部 react 分支（`build_tools` 恒构建原 ReAct 工具集、`get_max_tool_loops` 恒返回原 react 值）；`default_proofread_one` 签名移除 `react_mode` 参数及其回退分支。
2. **提示词只走 `agent_prompt_lines`**：`get_question_prompt()` / `get_review_prompt()` 删除 `question_prompt_lines` 回退；`agent_lines` 缺失/为空时 `raise ValueError`（提示修复配置后重新发起校对）。
3. **`question_prompt_lines` 字段删除**：7 个 `config.json` 删除该字段；`config_schema` 删除必填校验与标准化拷贝。
4. **`agent_prompt.json` 必填化（fail-fast）**：`config_schema` 中该文件缺失、`agent_prompt_lines` 为空或非法均累计为加载错误，`validate_config` 抛 `ValueError`，不再静默警告跳过。
5. **UI 开关移除**：删除「ReAct 模式」复选框、`react_enabled` 变量与 `_on_react_toggled` 回调；顺带清理无读取点的 `self.system_prompt` 遗留变量。
6. **副本/脚本同步**：`scripts/preview_react_prompt.py`、`scripts/test_e2e_agent_pipeline.py` 删除 `react_mode=True` 设置行。

## 影响

- `core/config_schema.py`、`core/base_subject.py`、`core/defaults.py`、`ui/default_app.py`
- 7 个学科 `subject.py` 与 `config.json`（删字段）
- 测试：`test_config_schema` / `test_config_loader` / `test_base_subject` / `test_subjects_consistency` / `test_math_v3_standalone` / `test_prompt_quality` / `conftest` 同步；删除「非 ReAct 模式」用例，新增 `agent_prompt.json` 必填（缺失报错、空数组报错）用例
- 文档：CONTEXT.md 状态句同步；ADR-0005 / ADR-0015 中回退机制相关决策被本 ADR 替代

## 不做的事

- 保留 `knowledge_agent_prompt_lines` 可选字段（与本次机制无关的遗留）
- 不删除 `config.json` 中其他字段（lecture_split / exam_split 等）
- 不改动 agent_prompt.json 内容本身（各学科提示词维持上一轮统一后的现状）