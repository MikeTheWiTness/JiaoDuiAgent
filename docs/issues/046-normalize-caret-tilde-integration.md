# 046 — 新增 normalize_caret_tilde 并全线集成（ADR-0020 C2 + Bug 1 + Bug 3）

**What to build:** 实现 `normalize_caret_tilde` 函数，将 pandoc 的 `^x^`/`~x~` 上下标记法统一转为 `<上标>`/`<下标>` XML 标记，并确保试卷、讲义两条管线都受益。同时修复 enhancer 的过度注入问题。

**Blocked by:** 045 — 删完死代码后新逻辑替换更清晰。

**Status:** done (commit 3173b29)

- [x] 在 `core/defaults.py` 新增 `normalize_caret_tilde(content)`，按正确顺序执行四步：`~x~`→`<下标>` → `^x^`→`<上标>` → `\~`→`~` → `\^`→`^`（lookbehind 保护 escaped 字符）
- [x] 在 `shared/docx_format_enhancer.py` 的 `inject_format_markers` 中跳过 `"subscript"` 和 `"superscript"` 类型（不删 `_FMT_MARKERS` 条目，保留 strip 能力）
- [x] 将 `normalize_caret_tilde` 集成到 `default_convert_file_to_md`（`enhance_docx_conversion` 之前），确保讲义模式也受益
- [x] 更新 `post_process_md_zw` 使用 `normalize_caret_tilde`
- [x] 验证：试卷模式 `t^2^`→`t<上标>2</上标>`，讲义模式上下标不丢失，`strip_format_markers` 仍能清洗
