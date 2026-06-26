# [#1] 修复 default_proofread_one 文件选择逻辑（精确匹配目录名）

**类型**: AFK | **阻塞**: 无 | **状态**: 待领取

## Parent

[ADR 0004：识典古籍 Playwright 集成与正文精确截取](../adr/0004-shidianguji-playwright-integration.md) — 决策 4

## What to build

`default_proofread_one()` 目前用 `os.listdir` + `break` 选取目录中第一个 `.md` 文件，不检查文件名与目录名是否一致。改为精确匹配：只读取 `{q_dir}/{q_name}.md`。

## Acceptance criteria

- [ ] `第1题/` 下同时有 `第1题.md` + `第1题_clean.md` + `_校对报告.md` 时，始终读到 `第1题.md`
- [ ] `q_name` 含特殊字符不崩溃
- [ ] 无同名 `.md` 时返回明确错误
- [ ] 现有单 `.md` 场景不受影响

## Blocked by

None - can start immediately.
