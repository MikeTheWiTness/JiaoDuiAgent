# Issue 016：API Provider 抽象化

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 7：API Provider 硬编码

## What to build

将 `call_api` 中硬编码的 OpenAI 兼容格式（`/chat/completions` 路径、`Bearer` 认证）抽象为 Provider 接口，支持切换 API 提供商不修改核心代码。

**问题**：当前 `call_api` 硬编码了 OpenAI 兼容的请求格式和认证方式。如果要切换到其他 API 提供商（如 Anthropic、本地模型），需要直接修改核心代码，风险高且不利于实验对比。

**修复方向**：
1. 定义 `BaseProvider` 抽象基类：
   - `build_url(base_url) → str`
   - `build_headers(api_key) → dict`
   - `build_payload(model, messages, tools, ...) → dict`
   - `parse_response(resp) → dict`
2. 实现 `OpenAICompatibleProvider`（当前行为）
3. `call_api` 接收 Provider 实例而非直接构造请求
4. Provider 类型通过配置指定，默认 OpenAI 兼容

**涉及文件**：
- `core/api_client.py` — `call_api` 改造
- 新增 `shared/providers.py` — Provider 接口 + OpenAI 实现
- `core/config_loader.py` — provider 类型配置

## Acceptance criteria

- [ ] `BaseProvider` 抽象基类定义完整（至少含 build_url / build_headers / build_payload / parse_response）
- [ ] `OpenAICompatibleProvider` 实现，行为与当前硬编码完全一致
- [ ] `call_api` 通过 Provider 实例发起请求，不再硬编码 `/chat/completions` 和 `Bearer`
- [ ] 现有所有校对流程端到端通过，无回归

## Blocked by

None - 远期需求驱动，可随时独立开始
