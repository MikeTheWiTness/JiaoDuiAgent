 # 002: PlanUpdateTool（LLM 自主管理校对计划）
 
 ## Parent
 
 ADR-0005；参考 Claude Code `src/tools/TodoWriteTool/` 的 TODO 工具模式
 
 ## What to build
 
 新增 `PlanUpdateTool`，LLM 通过工具调用来声明和管理校对计划状态（替代自由文本 `## 校对计划`）：
 
 - 数据结构 `{content: str, status: "pending"|"in_progress"|"completed", activeForm: str}`
 - LLM 首轮调用 plan_update 声明计划步骤，后续每完成一步更新状态
 - 强制规则：恰好 1 项 in_progress；完成即标记；不可批处理
 - **Verification Nudge**：全部 completed + 3+ 项 + 无 verification 步骤 → 工具返回值追加自查提示
 - 工具返回 `{ok, oldTodos, newTodos, nudge}`
 
 ## Acceptance criteria
 
 - [ ] LLM 能通过 plan_update 声明、更新、完成计划步骤
 - [ ] 恰好 1 项 in_progress 的约束有效
 - [ ] 全部 completed 时返回自查 nudge
 - [ ] 工具调用记录可被 UI 层读取用于进度显示
 - [ ] 与现有 BaseTool 框架兼容
 
 ## Blocked by
 
 None - 可立即开始（独立工具模块，与 call_api 并行开发）
