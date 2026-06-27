 # 003: 格式审查二级制
 
 ## Parent
 
 ADR-0005
 
 ## What to build
 
 实现二级制格式审查：
 
 **第一级（程序检查）**：
 - `_enforce_format` 重写：在 `### 标记原文` 和 `### 修改原因` 段落区域内分别计数
 - 编号集合一致性检查（非简单计数对比）
 - 标记格式完整性检查（`【` 后缺少 `编号|` 的情况）
 
 **第二级（LLM 格式修正）**：
 - `_llm_format_fix`：调用 `call_api_continue`（无工具）+ 精简格式修正 prompt
 - 仅重组格式，不改校对结论
 - 修正后再次检查；仍不合格 → 标记警告不阻塞
 
 整体流程接入 `default_proofread_one`。非 ReAct 模式同样生效。
 
 ## Acceptance criteria
 
 - [ ] 不误匹配正文中的 `1. ` 编号行（限 `### 修改原因` 区域内计数）
 - [ ] 标记编号与原因编号不一致时准确报错
 - [ ] `_llm_format_fix` 修正后格式合规率 > 80%
 - [ ] 修正后仍不合格不阻塞流程
 - [ ] 非 ReAct 模式下同样生效
 
 ## Blocked by
 
 - #001（需要 call_api_continue 和 messages 返回）
