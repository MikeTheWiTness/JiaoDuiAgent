# ADR 0024：latex_generator 大函数 pipeline 化 + 内部重复去重

**状态**：已实现（commit 16d7fcf）（C5+C4+C1 已完成，C2+C3 为内部抽取优化）
**日期**：2026-07-23（2026-07-24 修订：增"严格保留原差异 / log 输出逐字不变"两条原则；C2 删除"顺手补兜底"的修复构思——它是行为变更不是 refactor）
**决策者**：MikeTheWiTness
**关联**：[[ADR 0020 斜体/上下标分离修复]](0020-math-italics-separation.md)

## 范围原则（2026-07-24 审查加）

本 ADR 是纯重构优化，**不改任何可观察行为**。两条贯穿全 ADR 的纪律：

- **严格保留原差异**：抽公共函数/常量去重时，若多个使用点的字面量/逻辑略有不同，**差异一律保留**，不强行统一字面。逐字相同才合并。
- **`log()` 输出文本逐字不变**：用户可见的 UI 日志面板文本（含 emoji、缩进、截断长度）与现状逐字一致。重构过程中不新增、不删、不改写任何 `log(...)` 调用的字符串。

---

## 背景

`shared/latex_generator.py` 1408 行，承载校对后文本到 LaTeX 的全部变换。架构审查发现三块核心债务：

1. **`build_paracol_content`(1000-1204) ~205 行单函数**串联十余种文本变换（剥思考段 → 清 Pandoc span → 修 XML 标签 → 剥反斜杠转义 → 提图 → 提引号 → 提批注 → 修转义方括号 → 内联标记 → heading→bold → 格式标记 → escaping → 还原占位符 → 缺字兜底 → 换行 → 标记 → 右栏拼接），每一步都有顺序依赖与前提条件，全靠注释维护"必须在 X 之前"，无类型/顺序约束。

2. **`_process_inline_markers` 的 `_repl` ~110 行**（596-804）：含 5 段近乎相同的 `$...$` / `$$...$$` / `\(...\)` / `\[...\]` 处理分支（631-709），每段重复"剥定界符 → 判断是否仍含 $ → 占位符 + `\corrmark{...}{N}`"模板，逻辑高度重复且互不一致——`\(...\)` / `\[...\]` 分支没做 `'$' in inner` 兜底，而 `$...$` / `$$...$$` 分支有，是潜在边缘 bug。

3. **多处重复**：
   - `_escape_math_chars_outside_math`(836-921) ~85 行的 `^` 与 `_` 段近乎对称复制，仅命令名不同（`\textasciicircum{}` / `\textunderscore{}`）。
   - 粗/斜体正则 `r'\*\*(.+?)\*\*'` / `r'(?<!\*)\*([^*\n]+?)\*(?!\*)'` 在 `latex_generator.py:233、398、481` 三处各定义一份。
   - `_get_section_name`(1252-1256) 又手写一份 7 字符转义表，与 `_LATEX_SPECIAL`(44-60) 重复（`_LATEX_SPECIAL` 含 `\`→`\textbackslash`，对 section 名不合适）。
   - `_fix_missing_chars`(945-995) 的 `_keep` 白名单与前面的 replace 用两套"保留集"耦合，且 `'①②③...⑳'` 字符串在 `_keep` 与第 959 行重复。
   - 三处对"批注标记"的语法各有定义：`docx_comments.py`、`latex_generator.py:238`、`latex_generator.py:1028`。

## 决策

### C1：`build_paracol_content` 改造为 pipeline 步骤列表

抽出模块级 `_PIPELINE = [(name, fn), ...]` 列表，每步为纯函数（签名 `(state: _RenderState) -> _RenderState` 或 `(text, state) -> text`）。`build_paracol_content` 退化为按序调用 pipeline 并维护中间产物。

**关键纪律**：
- 每步独立可单测——传入构造好的 `state`，断言该步输出。
- 顺序依赖从"注释承诺"变为"列表顺序"——列表一旦定义，顺序即契约。
- **中间产物的落盘（AGENTS.md 要求）只落文件，不新增 `log` 输出**——按范围原则 "log 输出逐字不变"，pipeline 内部绝不向 UI 日志面板新增任何字符串。若出错需要诊断，沿用现状的完整 `log(traceback.format_exc())`，不在正常流程中调整 log 文本。

**不引入**：不强行把每步做成无副作用的"输入 immutable → 返回新对象"——文本变换本质上是可变状态流转，引入 immutable 会让每步都拷贝大字符串，性能不优。`_RenderState` 是普通 dataclass，可变字段，每步就地修改。可测性不打折——每步测的是给定 `_RenderState` 进入时的断言。

### C2：`_process_inline_markers` 统一定界符分支（严格按现状差异搬运）

抽 `_wrap_corrmark_math(num, inner, open_d, close_d, in_math) -> str` 统一处理四类定界符分支。**注意**：四分支现状存在**实际差异**——`$...$`、`$$...$$` 分支做 `'$' in inner` 兜底；`\(...\)`、`\[...\]` 分支**不做**此兜底；且四分支分别使用 `r"\("`/`r"\["` 不同的 LaTeX 包裹字符。

**抽取 ≠ 对齐**：抽公共函数时不强行抹平这些差异。重构需以**保留四分支逐字行为**为核心——公共函数接收参数表达差异（含 `with_dollar_guard: bool`、`wrap_open: str`、`wrap_close: str` 等），调用点按现状传入。

**明确不补兜底**（2026-07-24 审查）——原 ADR 草案提"顺手补齐 `\(...\)` / `\[...\]` 的 `'$' in inner` 兜底"，审查判定这是**bug 修复而非 refactor**：会改变不处理的 inner 增加新分支行为，违反"不改功能"。若未来确证是 bug，应单独立 issue 修复，不在本 ADR 范围内。

### C3：`_escape_math_chars_outside_math` 对称段抽取

抽 `_consume_braced_superscript(text, i, marker_cmd) -> (new_text, new_i)` 一处实现，`^` 与 `_` 两处调用。`marker_cmd` 区分 `\textasciicircum{}` / `\textunderscore{}`。状态机可优先考虑用小的 `(state, transition)` 表替代长 if-elif，便于单测，但这一步是 C3 的可选优化，不是硬要求。

### C4：重复正则与表去重（字面比对先行）

**字面比对先行原则**——所有去重抽取前必须先做 grep 比对：使用点的字面正则/常量**逐字相同**才合并；不同处一律保留（按范围原则"严格保留原差异"）。

- 粗/斜体正则：`latex_generator.py:233、398、481` 三处已核实均为 `r'\*\*(.+?)\*\*'` / `r'(?<!\*)\*([^*\n]+?)\*(?!\*)'`——字面相同，提模块级 `_BOLD_RE` / `_ITALIC_RE`，三处改 import。
- `_get_section_name` 的 7 字符转义表与 `_LATEX_SPECIAL`（含 `\`→`\textbackslash`，对 section 名不合适）拆成"全文转义表"与"文件名转义子集"两个常量——两份表字面不同，**保留差异**，仅消除手抄复制（同原 ADR 表述）。
- `_fix_missing_chars` 抽 `_FALLBACK_SYMBOLS = {'★','☆','…','①'…'⑳'}` 单一常量同时驱动 replace 与 `_keep` 过滤。
- `_UNICODE_MATH_MAP`（Unicode→LaTeX）与 `_MATH_ONLY_RE`（命令名集合）从单一映射 `SYMBOL → (latex_cmd, is_math_only)` 派生。原两份表覆盖同一批符号但需手工对齐；单源派生后由数据驱动派生，杜绝漂移。派生后两份派生物行为应与现状一致——落地时做"派生前 vs 派生后" 端到端测试比对，确认无 symbol 漏列或行为差异。
- `_get_section_name` 的 7 字符转义表与 `_LATEX_SPECIAL` 拆为"全文转义表"（含 `\`→`\textbackslash`）与"文件名转义子集"两个常量——明确两套表语义不同，但消除手抄复制。
- `_fix_missing_chars` 抽 `_FALLBACK_SYMBOLS = {'★','☆','…','①'…'⑳'}` 常量，同时驱动 replace 与 `_keep` 过滤，单一真源。
- 抽 `_UNICODE_MATH_MAP`（Unicode→LaTeX）与 `_MATH_ONLY_RE`（命令名集合）从单一映射 `SYMBOL → (latex_cmd, is_math_only)` 派生，消除两份表覆盖同一批符号需手工对齐的脆弱性。

### C5：批注标记统一（严格保留三处原差异）

抽 `shared/comment_marker.py`（新模块）统一 `<批注 id=N>...` 标记的正则、构造、解析函数。`shared/docx_comments.py`、`shared/latex_generator.py:238/1028` 三处改 import。

**严格保留三处原差异**——三处对"批注标记"的 matched group 数、子结构（含 `<原>...</原><改>...</改>` 内嵌）、flags（`re.DOTALL` 与否）参差不一致：
- `docx_comments.py`：`<批注\s+id=\d+>.*?</批注>`（带 DOTALL）
- `latex_generator.py:238`：`<批注\s+id=(\d+)><原>(.*?)</原><改>(.*?)</改></批注>`（含三个捕获组，无 flags 显式标注）
- `latex_generator.py:1028`：`<\s*批注\s+id\s*=\s*(\d+)\s*>`（补全格式化模式，无闭合匹配）

抽 `shared/comment_marker.py` 时必须把这三套**分别独立保留**——`comment_marker.py` 暴露三条对应函数/常量（如 `annotate_full_re` / `annotate_with_correct_re` / `annotate_open_tag_re`），三个使用点对应 import。**不强行把三处统一为单条正则**——它们语义不同（注释化全匹配 vs 含原改子字段 vs 补全标签）。本 ADR 的真源同步是"模块同一源"而非"语法同一正则"。

**同时抽 `_INLINE_MARKER_RE = re.compile(r'【\d+\|.*\|[^】]*】')`** 给 `core/parsing.py:157/162/170` 与 `core/format_enforcement.py:36` 复用。此处四处重复正则字面相同（已核实）——合并为单一定义，使用点 import；**这处合并字面字面相同，无差异需保留**。这一项与 call_api 重构解耦，可在本支线一起做。

## 明确不做（本支线范围外）

- **`latex_generator.py` 整体拆模块**：1408 行虽大但所有函数围绕同一变换流水线，内部聚合度高。拆成多个文件（如 `_latex_inline.py` / `_latex_error.py`）会引入跨文件状态流转，得不偿失。本支线只内部 pipeline 化，不动文件边界。
- **latex_generator 当前未导出函数的类型注解**：补类型注解工作量独立且与重构正交，留给日后小型补丁。
- **`pdf_compiler` 拆函数**：归 [[ADR 0025]](0025-pdf-compiler-split.md)（待写），与本文 latex_generator 不属同一改动集。

## 影响

### 正面

- `build_paracol_content` 每一步可独立单测——目前该函数整段只能黑盒端到端测试，pipeline 化后任意步骤都能被工厂测试触达
- `\(...\)` / `\[...\]` 分支的 `'$' in inner` 兜底补齐，修一个潜在边缘 bug
- 3 处粗/斜体正则、3 处批注标记、2 处转义表、2 份化学数学符号表 / 2 套保留集合，一并消除
- 中间产物可独立单测，不再只能黑盒端到端——这是工程化基线 ADR-0027 ruff/exc grill 后的回归价值所在
- 范围原则（严格保留原差异 / log 逐字不变）作为纪律内嵌，避免抽公共函数时人手"对齐差异"破坏现状行为

### 负面 / 风险

- **`build_paracol_content` 是已被既有测试覆盖的关键函数**——端到端测试虽有，但 pipeline 改造时若步骤边界划错（顺序、中间状态字段），可能短期内引入回归。**实施纪律**：先保留既有端到端测试不动，作为回归网；pipeline 拆完后再补步骤级单测。两阶段，禁止"拆完即删端到端测试"。
- **`_RenderState` 字段需精心设计**：若字段不齐，会让步骤间传递隐式状态变量。落地时第一步就是定 `_RenderState` 的字段清单——这是本次重构最容易欠考虑的部分，预留充分设计时间。
- **抽 `shared/comment_marker.py` 影响 3 个文件**：跨模块坐标，落地时需 grep 全仓 `<批注` 调用点确认完整。

### 实施顺序约束

1. **C5 批注标记统一 / 内联 marker 正则**最先做——独立、低风险、为后续步骤测试铺路。
2. **C4 重复正则与表去重**次之——机械抽取，风险低。
3. **C1 pipeline 化**是主干，先定 `_RenderState` 字段再做拆分；保留端到端测试作回归网。
4. **C2 + C3** 在 C1 pipeline 化稳定后做（这两块是 pipeline 内的重复消除）——`_wrap_corrmark_math` 与 `_consume_braced_superscript` 是内部分支的抽离，不需动外部 pipeline。
5. **C2 补齐 `'$' in inner` 兜底**是 bug 修复，必须有配套回归测试（能含 `$` 的 `\(...\)` 输入）。