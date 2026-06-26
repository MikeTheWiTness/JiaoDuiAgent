# [#5] 识典集成进校对链路（端到端）

**类型**: AFK | **阻塞**: #2 #3 #4 | **状态**: 待领取

## Parent

[ADR 0004：识典古籍 Playwright 集成与正文精确截取](../adr/0004-shidianguji-playwright-integration.md) — 全部决策

## What to build

将 #3 (Playwright 模块) 和 #4 (截取算法) 集成进 `search_original_text` 和 `preprocess_for_proofread`，实现端到端的识典古籍自动化校对。

具体改动：
1. `search_original_text` 文言文分支最前面插入识典优先（#3 可用时，取前 10 字搜索）
2. 搜到原文后调 #4 截取节选范围
3. `preprocess_for_proofread` 优先读 `_clean.md` 做搜索（回退现场清洗）
4. 0 差异 → 标记一致性，跳过文言文 LLM 校验；有差异 → 注入参考段

## Acceptance criteria

- [ ] 文言文题目自动从识典提取原文并注入 prompt 前置参考段
- [ ] Playwright 不可用时自动回退到现有 ddgs → web_fetch 链路
- [ ] `_clean.md` 不存在时回退到现场 `_clean_annotations()` 兜底
- [ ] 搜索关键词取前 10 个汉字
- [ ] 0 处差异 → prompt 标记「✅ 与识典古籍原文一致」，LLM 不需再校文言文部分
- [ ] 有差异 → 差异列表注入 prompt，LLM 判断真错 vs 异文
- [ ] 端到端实测：韦凑传校对 → 识典原文准确注入

## Blocked by

- [#2 `_clean.md` 全链路生成](02-clean-md-pipeline.md)
- [#3 Playwright 识典古籍提取](03-playwright-shidianguji-module.md)
- [#4 difflib 节选截取算法](04-excerpt-extraction-algorithm.md)
