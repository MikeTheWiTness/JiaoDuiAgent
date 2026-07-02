# Issue 011：API 用量追踪（token 统计 + 成本日志）

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 2：零 API 用量追踪

## What to build

在每次 API 调用的响应中提取 `usage` 字段（`prompt_tokens`、`completion_tokens`、`total_tokens`），写入日志和中间产物，实现 per-call 和 per-question 的成本可观测性。

**问题**：当前 `call_api` 完全不读取 API 响应中的 `usage` 字段，导致：
- 无法判断某次校对是否成本异常
- 无法在连续失败时基于成本信号熔断
- 无 per-question / per-session 成本报表

**修复方向**：
1. 在 `call_api` 的 `resp.json()` 后提取 `usage` 信息
2. 通过 `log()` 输出单次调用的 token 消耗
3. 在 `_校对报告.md` 中追加 token 统计段落
4. 在 `default_proofread_one` 中汇总本题目所有 API 调用的总消耗

**涉及文件**：
- `core/api_client.py` — 提取 usage + 日志输出
- `core/defaults.py` — 汇总 per-question 消耗，写入 `_校对报告.md`

## Acceptance criteria

- [ ] 每次 `call_api` 调用后，日志中输出 `prompt_tokens` / `completion_tokens` / `total_tokens`
- [ ] `_校对报告.md` 末尾包含本次校对的总 token 消耗统计
- [ ] `default_proofread_one` 汇总单题所有 API 调用的 token 总量
- [ ] 现有校对流程不受影响，无回归

## Blocked by

None - 可立即开始
