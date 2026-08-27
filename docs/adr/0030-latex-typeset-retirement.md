# ADR 0030：LaTeX/PDF 排版下线，仅保留 Word 排版

**状态**：已接受（实现随本批次 commit 落地）
**日期**：2026-08-27
**决策者**：MikeTheWiTness
**关联**：[[ADR 0024 latex_generator pipeline 重构]](0024-latex-generator-pipeline-refactor.md)、[[ADR 0025 pdf_compiler 拆分]](0025-pdf-compiler-split.md)、[[ADR 0020 斜体/上下标分离]](0020-math-italics-separation.md)

---

## 背景

排版输出长期存在两条并行路径：

- **PDF 路径（LaTeX）**：`shared/latex_generator.py` 渲染 paracol 双栏 `.tex` → `shared/pdf_compiler.py` 两步编译（xelatex → xdvipdfmx）→ 便携 TeX Live（`tools/build_minimal_texlive.py`）随 exe 打包，目标机器无需安装 TeX Live 即可出 PDF。
- **Word 路径**：`core/docx_report.py` 用 pandoc 将各题 `_校对报告.md` 合并为 docx，`$...$` 数学记法经 pandoc texmath 转为 Word 原生公式（OMML），修改意见注入为 Word 批注。

维护代价集中在 LaTeX 路径：便携 TeX 提取流程复杂（`.fls` 依赖追踪、字体映射、dvipdfmx 配置、`~15` 个 TEXMF 环境变量）、打包体积约 80 MB/学科、CJK 路径与字体缺失问题反复出现。2026-08-13 代码审查（`docs/notes/code-review-2026-08-13.md`「决策更新」）已非正式决定 LaTeX 排版功能下线，本书面化并落地。

## 决策

**LaTeX/PDF 排版链路整体下线，排版输出仅保留 Word 批注报告。**

### 删除

- `shared/latex_generator.py`（Markdown → .tex 渲染与 PDF 编排）
- `shared/pdf_compiler.py`（xelatex + xdvipdfmx 两步编译、便携版发现）
- `shared/templates/proofread_template.tex`（LaTeX 模板）
- `tools/build_minimal_texlive.py`（便携 TeX 构建器，构建期工具）
- UI「生成 LaTeX PDF 校对报告」勾选、`show_pdf_option` 特性开关、`generate_pdf` 参数全链（`ui/default_app.py`、`core/defaults.py:default_proofread_one`、`core/base_subject.py:proofread_one`）
- 校对完成后汇总 PDF 逻辑与「仅排版」入口的 PDF 分支（入口保留，只生成 Word）
- 打包链路：spec 中 templates datas、latex_generator/pdf_compiler hiddenimports；packaging.md 便携 TeX 章节
- 学科提示词中「避免 \\textbf{}、\\text{} 等 LaTeX 排版命令」指令（物理/化学）
- 测试：`test_latex_generator.py`、`test_math_pdf.py`、`test_marker_interleaving.py`；重写依赖 `generate_pdf` 的用例（typeset/behavior/proofread_one/subprocess_timeout/normalize_caret_tilde 等）

### 保留（Word 链路的组成部分，不属于 LaTeX 排版）

- `$...$`/`$$...$$` **数学记法**——它是 pandoc texmath → Word OMML 公式的输入格式；学科提示词中所有 `$...$` 标记规则原样保留
- `core/docx_report.py`（pandoc md→docx + 批注注入）、`shared/formula_render.py`（matplotlib 渲染批注公式 PNG，失败降级为文本）、`shared/comment_marker.py`、`shared/docx_comments.py`、`shared/docx_format_enhancer.py`
- `core/pandoc_utils.py`（docx→md 导入与 find_pandoc）
- `core/defaults.py:fix_latex_escapes`——纯文本处理：还原 pandoc 过度转义、保护数学块，是 Word 公式识别与 md 文本质量的前提，不依赖任何 TeX 引擎
- UI「排版」管线阶段与「仅排版」入口（对已有校对目录补出 Word 报告），管线校验文案改为 Word 语义

### 派生变化

- `default_proofread_one`/`proofread_one` 签名删除 `generate_pdf`；格式修正由 `enable_format_fix` 显式控制（UI 传 True，默认 False）
- CI 不再需要 TeX Live；`ADR-0019 C6.4` 的 latex 环境 skip 守卫随 `test_math_pdf.py` 删除
- 打包：单步 `pyinstaller`，体积口径约 120 MB/学科

## 影响

- **用户**：不再生成 LaTeX 双栏 PDF 报告；Word 批注报告成为唯一排版产物（公式仍为 Word 原生公式）
- **学科**：7 科全部走共享 UI 与共享生成器，行为一致；仅提示词删两处 LaTeX 排版命令指令、config 措辞「空 LaTeX 环境」改「空公式环境」
- **ADR 0024 / 0025**：其重构对象（latex_generator / pdf_compiler）随功能下线整体删除，状态翻转为「已废弃」
- **ADR 0020**：C1/C4/C5 的 LaTeX 专属行为失效，但 C2（normalize_caret_tilde）/C3 仍服务 Word 链路，保留