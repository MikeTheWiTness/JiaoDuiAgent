 # 005: 文本导航工具 + 前置搜索协调
 
 ## Parent
 
 ADR-0005
 
 ## What to build
 
 新建文本导航工具模块，调整前置搜索 hook 在 ReAct 模式下的行为：
 
 - `shared/text_nav_tools.py` 新建：`LocateParagraphTool`（关键词定位 → 返回段落 + 上下文）、`ReadSectionTool`（段落编号 → 返回完整文本）。通过类属性注入当前题目 md_text
 - `default_proofread_one`：ReAct 模式前置 hook 成功后不 `tools=[]` 关闭工具
 - `chinese_classics_tools.py` 的 `build_reference_section()` 约束行从"严禁"改为"建议"
 
 ## Acceptance criteria
 
 - [ ] LocateParagraphTool 正确定位关键词并返回上下文
 - [ ] ReadSectionTool 正确返回指定段落范围
 - [ ] ReAct 模式下前置搜索后 LLM 仍可调用其他工具
 - [ ] 约束行措辞为建议性（LLM 不困惑）
 - [ ] 非 ReAct 模式下行为不变
 
 ## Blocked by
 
 - #001（需要上下文注入机制）
