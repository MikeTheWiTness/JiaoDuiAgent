 # 006: UI 集成 + max_loops + 中间产物 + 全链路连通
 
 ## Parent
 
 ADR-0005
 
 ## What to build
 
 将所有 ReAct 组件连通为完整端到端流程：
 
 - `ui/default_app.py` 新增 ReAct 复选框（默认开启），连接 `subject_app.react_mode`
 - 进度面板：从 PlanUpdateTool 的 tool_calls_log 记录读取每个步骤的状态，在日志面板中渲染为 TODO 列表
 - max_loops：高中语文 3→15，高中物理 20→30
 - `default_proofread_one` 新增落盘：`_校对计划.md`（PlanUpdateTool 最终状态）、`_对话历史.json`（完整 messages）
 - 高中物理 `config.json` 新增 `agent_prompt_lines` 初版
 - 端到端测试
 
 ## Acceptance criteria
 
 - [ ] UI 复选框默认开启，切换即时生效
 - [ ] 进度面板从 PlanUpdateTool 调用记录正确渲染 TODO 列表
 - [ ] ReAct 模式下语文 max_loops=15，物理=30
 - [ ] `_校对计划.md` 包含 PlanUpdateTool 最终状态
 - [ ] `_对话历史.json` 包含完整 messages
 - [ ] 高中物理 agent_prompt_lines 可正常加载
 - [ ] 端到端无报错
 
 ## Blocked by
 
 - #001（call_api 改造）
 - #002（PlanUpdateTool）
 - #003（格式审查）
 - #004（agent prompt 基础设施）
