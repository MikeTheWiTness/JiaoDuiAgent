 # 001: call_api 核心改造（State/Config 分离 + 压缩历史 + call_api_continue）
 
 ## Parent
 
 ADR-0005（ReAct 机制核心架构决议）；参考 Claude Code `src/query.ts` 的 State vs Config 分离模式
 
 ## What to build
 
 将 `call_api` 从"单一函数 + 三元组返回值"升级为职责分离的对话引擎：
 
 1. **State vs Config 分离**：不可变配置 `CallApiConfig`（url, key, model, max_turns）与可变状态 `CallApiState`（messages, turn_count）分开管理
 2. **StopReason 枚举**：显式停止原因（END_TURN / TOOL_LOOP / MAX_TURNS / ERROR）替代隐式 `finish_reason` 判断
 3. **返回值扩展**：从 `(content, tool_calls_log, reasoning)` 改为 dict `{"content": ..., "tool_calls_log": ..., "reasoning": ..., "messages": [...], "stop_reason": ...}`
 4. **压缩历史**：max_turns 或连续 3 轮空结果触发时，移除无效 tool_calls/tool_result 对，插入压缩摘要 user 消息，下一轮不带 tools 发起请求
 5. **call_api_continue()** 新增：接收已有 messages + 追加消息，单次请求，不启动工具循环（供格式修正使用）
 
 ## Acceptance criteria
 
 - [ ] call_api 返回值包含 messages 列表和 stop_reason
 - [ ] max_turns 超限时对话历史不丢失（压缩而非丢弃）
 - [ ] 连续 3 轮空/重复结果触发 TOOL_LOOP，执行压缩 + 去工具
 - [ ] call_api_continue 正确复现，不进入工具循环
 - [ ] 现有所有调用方适配新返回值（向后兼容）
 - [ ] 单元测试覆盖所有 StopReason 路径
 
 ## Blocked by
 
 None - 可立即开始
