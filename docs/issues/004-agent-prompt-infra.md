 # 004: agent_prompt_lines 基础设施 + 高中语文 ReAct prompt
 
 ## Parent
 
 ADR-0005；参考 Claude Code `src/constants/prompts.ts` 的工具使用指南密度
 
 ## What to build
 
 建立 agent_prompt_lines 的加载和切换机制，编写高中语文 ReAct prompt：
 
 - `config_loader.load_config()` 加载 `agent_prompt_lines`（可选，缺失不报错）
 - `subject.py` 新增 `react_mode` 属性（默认 False）；`get_question_prompt()` 和 `get_max_tool_loops()` 根据 react_mode 切换
 - 高中语文 `config.json` 新增 `agent_prompt_lines`，包含 PlanUpdateTool 使用指南（何时用/何时不用/示例，参考 Claude Code prompt.ts 密度）
 - 保留 `question_prompt_lines` 作 fallback
 
 ## Acceptance criteria
 
 - [ ] react_mode=False 时行为完全不变
 - [ ] react_mode=True 时 LLM 首轮调用 plan_update 声明计划
 - [ ] react_mode=True 时 max_loops=15
 - [ ] 工具使用指南含详细的"何时用/何时不用/示例"
 - [ ] 缺失 agent_prompt_lines 时 fallback 且不报错
 
 ## Blocked by
 
 - #001（call_api 已支持长对话）
 - #002（PlanUpdateTool 已存在，prompt 需要引用它）
