# Issue 053：API 接口格式可选 —— 支持 /responses

## What to build

校对主流程目前固定使用 OpenAI Chat Completions 兼容格式（`/chat/completions`）。部分模型/网关要求使用 OpenAI Responses API（`/responses`）。本 issue 在 API 配置界面新增「接口格式」选择，并让校对主流程、智能分割、格式修正、物理/化学独立解题等所有走 API 的链路按所选格式切换。

### 改动范围

- UI：API 配置对话框新增「接口格式」单选按钮（`/chat/completions` 默认、`/responses`）
- 配置：`.env` 增加 `API_FORMAT` 字段，读取与保存均保留默认 `chat/completions`
- 请求层：`call_api` 按格式拼接端点和转换请求/响应；Responses API 的工具调用、usage、reasoning 均归一化为 Chat Completions 风格，工具循环逻辑无需分叉
- 调用链：SessionContext、智能分割、格式修正、物理/化学独立解题透传所选格式

## Acceptance criteria

- [ ] API 配置界面出现「接口格式」选择，默认选中 `/chat/completions`
- [ ] 选择 `/responses` 后保存到 `.env`，重启后仍生效
- [ ] 校对主流程在 `/responses` 格式下可完成单轮与工具调用多轮对话
- [ ] 智能分割、格式修正、物理/化学独立解题在 `/responses` 格式下使用相同端点，不回落 `/chat/completions`
- [ ] 默认 `chat/completions` 行为与改造前完全一致（既有测试不改动即通过）
- [ ] 新增 Responses API 转换单元测试，全量 `pytest` 保持全绿

## Blocked by

None