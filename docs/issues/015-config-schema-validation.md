# Issue 015：配置 Schema 验证

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 6：配置无 Schema 验证

## What to build

为各学科的 `config.json` 定义 Pydantic 模型，在启动/加载时校验配置的必填字段、类型和值域，使拼写错误不再静默失效。

**问题**：当前 `config.json` 通过手动 `dict.get()` 读取，字段名拼写错误、类型不匹配等问题静默失效——不会报错，但功能异常。不同学科的配置结构也没有契约保证，新增学科时容易遗漏必填字段。

**修复方向**：
1. 定义配置 Pydantic 模型（覆盖所有学科的公共字段 + 各学科特有字段）
2. 在 `config_loader.py` 中加载后立即校验，不合格给出明确错误提示
3. 启动时校验，而非首次使用时才发现问题
4. 为所有现有学科的 `config.json` 生成对应的 schema 描述

**涉及文件**：
- `core/config_loader.py` — 加载后校验
- `subjects/*/config.json` — 各学科配置（仅校验逻辑，不修改配置内容）
- 新增 `shared/config_schema.py` — Pydantic 模型定义

## Acceptance criteria

- [ ] 定义所有学科的公共配置字段 Pydantic 模型（至少包含 `api_url`、`api_key`、`model`、`max_loops`、`question_prompt_lines`、`agent_prompt_lines`）
- [ ] 加载 `config.json` 后自动校验，字段缺失/类型错误立即报错并指明具体文件和字段
- [ ] 启动时（非运行时）即完成校验，不等到首次校对才发现配置问题
- [ ] 现有所有学科的 `config.json` 通过校验（或其问题被显式指出并修复）

## Blocked by

None - 可立即开始（与 ADR-0011 学科代码去重重构配合进行，但不互相阻塞）
