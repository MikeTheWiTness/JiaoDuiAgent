# 045 — 删除损坏的斜体转数学与波浪号修复函数（ADR-0020 C1 + C3）

**What to build:** 删除 `core/defaults.py` 中三个有缺陷的 markdown 后处理函数，简化 `post_process_md_zw` 调用链。这些函数是第12题颜色泄漏的根因或无用代码。

**Blocked by:** None — 可立即开始。

**Status:** done (commit 3173b29)

- [x] 删除 `convert_italics_to_math`（碎片公式 `$x$=$t^2^$+5$t$` 的源头）
- [x] 删除 `fix_tilde_in_math`（`\$[^$]+\$` 跨段落误配对，`0\sim2s` 的祸根）
- [x] 删除 `fix_tilde_in_text`（功能由 normalize_caret_tilde 覆盖）
- [x] 更新 `post_process_md_zw` 移除对这三个函数的调用
- [x] 全仓测试通过（580 passed, 0 failed）
