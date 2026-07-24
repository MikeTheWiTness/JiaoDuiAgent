# 047 — 斜体内部上下标处理 + _MATH_ONLY_RE 补充 sim（ADR-0020 C4 + C5）

**What to build:** 处理 `*v<下标>0</下标>*` 这种斜体包裹上下标的边界情况，在 `_extract_md_formatting` 的替换回调中直接转换 XML 标记为 LaTeX 命令。同时在 `_MATH_ONLY_RE` 中追加 `sim` 作为防御性加固。

**Blocked by:** 046 — 需要 `<上标>`/`<下标>` 标记已由 normalize_caret_tilde 产出。

**Status:** done (commit 3173b29)

- [x] 修改 `_italic_repl`，对捕获的 inner 做 `<上标>`→`\textsuperscript{`、`<下标>`→`\textsubscript{` 替换
- [x] 修改 `_bold_repl`，同样处理
- [x] 在 `_MATH_ONLY_RE` 的命令列表中追加 `|sim`
- [ ] 验证：`*v<下标>0</下标>*` 渲染为 `\textit{v\textsubscript{0}}`，`\sim` 漏入文本模式时自动 `$...$` 包裹
