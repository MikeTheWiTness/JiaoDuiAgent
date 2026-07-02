# Issue 014：SessionContext 封装（消除参数传递链）

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 4：参数传递链过长

## What to build

引入 `SessionContext` 数据类封装校对会话配置，在顶层注入，下游按需读取，消除当前 `api_url` / `api_key` / `model` 等参数经过 7 层函数显式传递的问题。

**问题**：`api_url`、`api_key`、`model` 从 UI 层到实际 API 调用经过约 7 层函数传递，每层都要显式声明这三个参数。新增配置项时改动面巨大，且容易在某层遗漏传递。

**修复方向**：
1. 定义 `SessionContext` 数据类：
   ```python
   @dataclass
   class SessionContext:
       api_url: str
       api_key: str
       model: str
       output_dir: Optional[str] = None
       max_loops: int = 20
       max_tokens: int = 16384
   ```
2. 在顶层（UI/入口）创建 `SessionContext` 实例
3. 下游函数接收 `ctx: SessionContext` 替代多个独立参数
4. 不改变函数的外部行为，仅重构参数传递方式

**涉及文件**：
- `core/api_client.py` — `call_api` 签名改造
- `core/defaults.py` — `default_proofread_one` 及内部函数
- `subjects/*/subject.py` — 各学科 Subject 类
- UI 层调用点

## Acceptance criteria

- [ ] `SessionContext` 数据类定义并包含所有会话级配置
- [ ] `call_api` 函数签名从 `(api_url, api_key, model, md_text, ...)` 改为 `(ctx: SessionContext, md_text, ...)`
- [ ] `default_proofread_one` 及其内部调用链不再逐层传递 `api_url` / `api_key` / `model`
- [ ] UI 层在入口处构造 `SessionContext`，后续不再重复传递
- [ ] 现有所有校对流程端到端通过，无回归

## Blocked by

建议在 Issue 011-013 稳定后进行——这些 issue 会修改 `call_api` 和 `default_proofread_one` 的内部实现，先让它们落定再重构参数传递方式，避免合并冲突。
