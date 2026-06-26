# [#4] difflib 节选精确截取算法

**类型**: AFK | **阻塞**: 无 | **状态**: 待领取

## Parent

[ADR 0004：识典古籍 Playwright 集成与正文精确截取](../adr/0004-shidianguji-playwright-integration.md) — 决策 2

## What to build

在 `shared/chinese_classics_tools.py` 中新增 `extract_excerpt_from_full(full_text, excerpt_text, margin=20)` 函数。

逻辑：
1. 去除标点 → `n_full` / `n_excerpt`
2. `difflib.SequenceMatcher` 对齐
3. 取第一个 match block 起、最后一个 match block 止
4. 两端各留 `margin` 字（可多不可少）
5. 映射回原始带标点位置 → 返回截取字符串

## Acceptance criteria

- [ ] 韦凑传全文(1197字) + 节选(593字) → 截取区间完全包含所有节选文字
- [ ] 节选与原文完全一致时，`margin=0` 下截取精确等于全文
- [ ] `margin=20` 时两端各多约 20 字上下文
- [ ] 节选在原文中找不到匹配时返回 `None`
- [ ] 单元测试覆盖上述场景

## Blocked by

None - can start immediately.
