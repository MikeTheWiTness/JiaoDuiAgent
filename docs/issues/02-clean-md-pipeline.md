# [#2] `_clean.md` 全链路生成（转换 + 切分）

**类型**: AFK | **阻塞**: #1 | **状态**: 待领取

## Parent

[ADR 0004：识典古籍 Playwright 集成与正文精确截取](../adr/0004-shidianguji-playwright-integration.md) — 决策 3

## What to build

在 Word→MD 转换阶段生成两份文件：`_raw.md`（含格式标记）和 `_clean.md`（完全去除标记的纯文本）。clean 版在切分时随 raw 版一起分发到各题目目录。

需改动两个位置：
1. pandoc 转换尾部生成 `_clean.md`
2. 切分写入时同步写 `第N题_clean.md`

## Acceptance criteria

- [ ] 转换后 `_clean.md` 不含任何 `【下划线】`/`【波浪线】`/`【着重】`/`[📝批注]` 标记
- [ ] `_clean.md` 正文文字量与 `_raw.md` 一致（仅去除了标记，不删文字）
- [ ] 每个 `第N题/` 目录下有 `第N题_clean.md`
- [ ] `_clean.md` 不存在不影响现有流程

## Blocked by

[#1 修复文件选择逻辑](01-fix-md-file-selection.md)
