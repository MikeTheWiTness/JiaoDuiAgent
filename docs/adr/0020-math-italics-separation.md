# ADR 0020：斜体/上下标脱离 $...$ 数学模式 —— 消除碎片公式引发的颜色泄漏与排版崩溃

**状态**：已实现（commit 3173b29）
**日期**：2026-07-22
**实现日期**：2026-07-23
**决策者**：MikeTheWiTness
**关联**：第12题大面积红字 + 排版错乱的线上故障分析

---

## 背景

### 线上故障

高一上月考卷1 的校对报告 PDF 中，**第12题出现大面积红色文字 + 排版崩溃**。根因分析如下：

| 环节 | 产出 | 问题 |
|---|---|---|
| Word 原文 | `x=t²+5t`（变量斜体 + 原生上标） | 正常 |
| pandoc docx→md | `*x*=*t^2^*+5*t*`（`*...*` 斜体、`^2^` 上标记法） | 正常 |
| `convert_italics_to_math` | `$x$=$t^2^$+5$t$` | **❌** 把每个斜体片段单独裹成 `$...$`，`^2^` 被一起包进数学模式 → `$t^2^$`（LaTeX 双上标错误） |
| `fix_tilde_in_math` | `0\sim2s` 替代 `0\~2s` | **❌** 正则 `\$[^$]+\$` 跨段落误配对，把纯中文文本当成公式，裸 `\~` 被错转为 `\sim`（数学命令掉进文本模式） |
| 校对标记注入 tex | `\corrmark{0\sim2s}{4}` | **❌** `\sim` 在文本模式非法 → LaTeX 错误恢复**删掉了 `\textcolor{red}` 颜色分组的闭括号** → 红色泄漏到整页；数学模式未正常退出 → 后续中文全部用拉丁字体排版 → 崩溃 |

同一机制也影响了第10题——`$\text{Δ}x = x_2 - x_1$` 中 `\text{Δ}` 因 pandoc 把 Unicode Δ 转为 `\text{\Delta}`（数学命令掉进 `\text` 文本环境）触发相同级联。

### 设计问题

`convert_italics_to_math`（`core/defaults.py:542`）的设计意图是：Word 中物理变量用斜体，应转为 LaTeX 数学模式以获得正确的数学斜体排版。但 Word 的斜体运行是**断续的**——只有字母是斜体，数字和运算符不是。这导致每个斜体片段变成独立的 `$...$` 块，产出碎片公式 `$x$=$t^2^$+5$t$`。

`fix_tilde_in_math` 的设计意图是：pandoc 可能产出 `\~` 在数学块内，需转为 `\sim`。但实际 pandoc 产出中 `\~` 只在文本中出现，`\sim` 直接出现在数学块内——此函数是空操作，但其粗粒度正则 `\$[^$]+\$` 会跨行/跨题错误配对。

---

## 决策

### C1：斜体保持 `*...*` 走文本模式，不转 `$...$`

**删除** `convert_italics_to_math`。

理由：
- LaTeX 文本模式斜体命令 `\textit{x}` 与数学斜体 `$x$` 对单个字母的视觉效果几乎无差异，均满足"变量用斜体"的物理排版规范
- `latex_generator.py` 已有的 `_extract_md_formatting` 会将 `*x*` → `\textit{x}`，转换链路完整
- 碎片公式问题根除：不再有 `$x$=$t^2^$+5$t$`
- Word 公式编辑器产出的真公式（分式、`\Delta`、`\sim` 等）来自 OMML → pandoc → `$$...$$`，不受影响，仍保留数学模式

### C2：上下标统一走 pandoc 记法 `^x^`/`~x~`，删除 enhancer XML 标记

**新增** `normalize_caret_tilde(content)`（`core/defaults.py`），按以下顺序处理：

```
1. ~x~ → <下标>x</下标>    regex: (?<!\\)~([^~\s]+?)~
2. ^x^ → <上标>x</上标>    regex: (?<!\\)\^([^\^\s]+?)\^
3. \~  → ~                （还原 pandoc 转义的字面波浪号）
4. \^  → ^                （还原 pandoc 转义的字面脱字号）
```

**删除** `docx_format_enhancer._FMT_MARKERS` 中的 `"下标"` 和 `"上标"` 条目。

理由：
- pandoc 已经用 `^x^`/`~x~` 完整表达 Word 上下标，enhancer 再注入 `<下标>x</下标>` 会产生 `^<上标>2</上标>^` 双重标记
- **顺序是关键设计**：先转 `^x^` → `<上标>`（用 lookbehind `(?<!\\)` 跳过 pandoc 转义号），再还原 `\^` → `^` 和 `\~` → `~`。若顺序反过来，还原后的 `^` 会和上标语法混淆
- 转换后产出的 `<上标>`/`<下标>` 作为统一中间标记，后续链路（latex_generator 的 `_convert_format_markers`）已支持映射到 `\textsuperscript`/`\textsubscript`

### C3：删除 `fix_tilde_in_math`

理由：
- pandoc 产出中 `\~` 仅出现在文本，`\sim` 直接出现在数学块——此函数是空操作
- 其 `\$[^$]+\$` 正则跨段落误配对是第12题 `0\sim2s` 的祸根

### C4：`_MATH_ONLY_RE` 补充 `sim`

`shared/latex_generator.py:546-548` 的命令列表中追加 `|sim`。

理由：防御性加固，确保任何可能漏入文本模式的 `\sim` 被自动包裹 `$...$` 避免 LaTeX 报错。

### C5：`latex_generator.py` 斜体内部上下标处理

在 `_extract_md_formatting` 的 `_italic_repl` / `_bold_repl` 中，对捕获的 inner 做 `<上标>`/`<下标>` → LaTeX 命令的转换。

理由：`*v~0~*` 在 C2 步骤后变为 `*v<下标>0</下标>*`。italic placeholder 提取时 inner = `v<下标>0</下标>`，需就地转换为 `\textit{v\textsubscript{0}}`。latex_generator 的 `_convert_format_markers` 在 `_extract_md_formatting` 之后运行（L1061→L1062），无法发现已 placeholder 化的 inner 中残留的 XML 标记。

---

## 后果

### 正面影响

- ✅ 碎片公式 `$x$=$t^2^$+5$t$` 消失，双上标 LaTeX 错误消失
- ✅ `0\sim2s` 类数学命令污染文本模式的问题消失
- ✅ 第12题的颜色泄漏 + 排版崩溃根除
- ✅ enhancer + pandoc 的双重标记（`^<上标>2</上标>^`）消失，标记链路统一
- ✅ `post_process_md_zw` 函数调用链从 5 步减为 3 步

### 负面影响与缓解

| 风险 | 缓解 |
|---|---|
| `\textit{x}` 与数学斜体 `$x$` 视觉微差 | 单字母几乎无差异；同一题内真公式 `$v_0$` 与 `\textit{x}` 混排风格略不同但可接受 |
| 删除 enhancer 上下标提取后，罕见情况下 pandoc 漏掉某个 Word 上标 → 丢失 | pandoc docx reader 对 `vertAlign` 的支持是基本功能，概率极低。如发生，校对 LLM 会收到文本而不报告错误，可由用户手动发现 |
| 现有测试无覆盖被删函数 | `convert_italics_to_math`、`fix_tilde_in_math` 全仓无任何测试引用，删除安全 |
| 删 enhancer 两条目影响 `_FMT_MARKERS` | 其他 5 个标记（着重号、下划线、波浪线、删除线、双删除线）不受影响；test_marker_interleaving 不涉及上下标条目 |

### 未解决

- 学科 prompt 中 `$...$` 公式约定的说明文字不受影响——真公式（OMML）仍用数学模式，斜体变量不再被要求放在 `$...$` 内，LLM 自然适应
- 阅读器（LLM）看到 md 中的 `<上标>`/`<下标>` 标记是新增的——校对 LLM 的 prompt 不引用这些标记，不予处理

---

## 备选方案

**方案 B：用 Unicode 上下标字符（²、₀）代替 LaTeX 命令。**
- 优点：无 LaTeX 依赖
- 缺点：Unicode 仅覆盖 0-9 单一数字，`v₁₀`、`a_{n+1}` 等无法表示；在不同字体中显示不一致

**方案 C：斜体保留 `*...*` 不转，上下标仍走 `$...$`。**
- 优点：上下标渲染质量最高（数学模式原生）
- 缺点：`*t^2^*`→`$t^{2}$` 需正则拆解 pandoc 记法再重建 LaTeX 上标语法，正则复杂且仍和 enhancer 双重标记冲突

选择主方案（C1-C5）因其改动最小、风险最低、且从根本上消除了碎公式和颜色泄漏两类 LaTeX 编译炸弹。
