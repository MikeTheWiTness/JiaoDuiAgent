# [#3] Playwright 识典古籍提取模块

**类型**: AFK | **阻塞**: 无 | **状态**: 待领取

## Parent

[ADR 0004：识典古籍 Playwright 集成与正文精确截取](../adr/0004-shidianguji-playwright-integration.md) — 决策 1

## What to build

新建独立模块 `shared/shidianguji_playwright.py`，封装 Playwright headless 浏览器从识典古籍提取正文的能力。软依赖设计——Playwright 不可用时静默不可用，不抛异常。

三个函数：
- `is_playwright_available()` — 探测 Playwright + Chromium
- `extract_chapter(book_id, chapter_id)` — 渲染详情页，提取 `article.chapter-reader` 中标题和段落
- `search_and_extract(keywords)` — 搜索识典 → 取第一条 → 提取全文

稳定要点：`wait_until="domcontentloaded"` + 等 `article.chapter-reader p`（不能用 `networkidle`）。

## Acceptance criteria

- [ ] Playwright 可用时，搜「韦凑字彦宗京兆万年人」返回韦凑传全文
- [ ] Playwright 不可用时 `is_playwright_available()` 返回 `False`，模块不抛异常
- [ ] 搜索页优先纯 HTTP（复用现有 `_parse_shidianguji_search`），取不到才 Playwright 渲染
- [ ] 无匹配结果时返回 `None`（不抛异常）
- [ ] 单次抓取 < 10 秒

## Blocked by

None - can start immediately.
