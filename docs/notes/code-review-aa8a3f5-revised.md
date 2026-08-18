# JiaoDuiAgent 项目全面审查报告（修订版）

> 审查基线：`HEAD aa8a3f5`（main）。审查方式为只读代码走查 + 针对性脚本复现；**审查过程中未修改任何仓库文件**（核查结束时的 `git status` 仅剩原有的未跟踪 `.vscode/`；本报告文件为审查完成后按用户要求落盘）。
> 基线复核（本修订版实际执行）：`pytest` 收集 **909** 项，执行 **868** 项全部通过（41 项按 marker 排除，用时 37s）；`ruff check` 全部通过；`pytest.ini` 与 `pyproject.toml` 双配置冲突告警实测存在（`WARNING: ignoring pytest config in pyproject.toml!`）。
> 相对上一版：修正 10 处事实性错判/不准确，新增 BashTool 相对路径穿越、换行/命令替换/`python -m` 绕过、API 对话记录中断路径与截断问题，并把测试盲区按“能否确定性红”重新标注。

---

## 总体判断

架构方向清晰（core/defaults/base_subject 分层、ADR 驱动、护栏测试较多），上一轮审查的多数 P0/P1 已修复。本次确认 **3 个高危行为错误/安全绕过（其中 BashTool 绕过面比上一版报告所列更宽）**、若干中危“行为与预期不符”，以及一批明确的**未实现、半落地和死代码**。

---

## 一、高危问题（建议优先修复）

### H1. BashTool 沙箱存在多重绕过（上一版仅列管道/分号，实际更宽）

- 位置：`shared/bash_tool.py:46-92`（校验）、`:122-138`（`shell=True` 执行）；生产调用 `core/format_enforcement.py:143-145`。
- 当前逻辑只取 `re.split(r'[;|&]', ...)[0]` 的首命令做白名单；`check_dangerous` 只在“首命令是 python 且带 `-c`”时执行；路径检查只拦“以 `/` 开头的独立 token”和 `cd`。

**H1-a：shell 分隔符只查首命令，`python -c` 危险代码免检（上一版已列，复核属实）**

以下命令**通过校验**（实测）：

```python
"echo hi | python -c \"import os; print(open('.env').read())\""
"echo hi; python -c \"import os; os.system('id')\""
"echo hi && python -c \"import os; print(1)\""
```

说明：上一版第三条示例 `cat /etc/hosts | python -c ...` 在生产传 `allowed_dir` 时会被绝对路径 token 检查拦截；但把 `/etc/hosts` 写进 `python -c` 引号内（如 `echo hi | python -c "import os; print(open('/etc/hosts').read())"`）即可绕过，结论不变。

**H1-b：换行、命令替换、`python -m`、脚本路径同样绕过（上一版遗漏）**

以下全部**放行**（实测）：

```text
echo hi
python -c "import os; ..."          # 换行分隔两条命令
echo $(python -c "import os; ...")  # $() 命令替换（反引号同理）
python -m http.server               # check_dangerous 只匹配 -c
python script.py                    # 脚本形态不扫描
```

**H1-c：`allowed_dir` 可被相对路径穿越（上一版完全遗漏，最直接的沙箱逃逸）**

以下在 `allowed_dir=/tmp/allowed_xyz` 下全部**放行**（实测）：

```text
cat ../secret.txt          → None（放行）
echo evil > ../../pwn.txt  → None（放行）
cp ../../x.txt .           → None（放行）
ls ../..                   → None（放行）
```

路径检查不拦截 `../`，Windows 盘符绝对路径（`C:\...`）也不在 `/` 检查覆盖内。

- 影响：格式修正链路（`core/format_enforcement.py` 的 `_bash_format_fix`）中，恶意文档内容可提示注入 LLM 后执行任意 Python、读绝对路径下的 `.env`（API Key，注意 `.env` 在学科目录而非 BashTool cwd 的“同目录”）或借助任意库外传；相对路径穿越还可直接读/写 `allowed_dir` 之外的文件。
- 建议：① 拒绝或完整词法解析所有 shell 多命令形态（`; | & &&`、换行、`$()`、反引号、重定向）；② 对每个命令片段分别做白名单 + `check_dangerous`，并把 `python -m`、`python <file>` 纳入扫描或直接禁用；③ `allowed_dir` 校验改为 `os.path.realpath` 归一化后必须落在允许目录内（拦 `..` 与符号链接穿越）；④ 补上述全部形态的回归测试。

### H2. `CheckEqualityTool` 把相反数判为相等（数学正确性错误）

- 位置：`shared/sympy_tools/templates.py:95-109`。
- `equality` 模板在 `a - b == 0` 和 `a.equals(b)` 都不成立后，又做 `a**2 - b**2 == 0` 兜底。实测：

```python
CheckEqualityTool()._run("x", "-x")
CheckEqualityTool()._run("sqrt(2)", "-sqrt(2)")
# 均 → {"success": true, "result": true, ...}
```

- 影响：物理/化学/数学校对中“表达式等价校验”出现假阴性，直接放过符号错误（`a` 与 `-a`、`v` 与 `-v`）。
- 建议：删除平方差兜底，或仅在可证明符号相同的前提下使用；补相反数、平方和等回归测试。

### H3. 打包后 `agent_prompt.json` 丢失，ReAct 模式静默退化

- 位置：`specs/高中物理.spec:16-24`、`subjects/高中物理v3.0/main.py:27-34`、`core/config_schema.py:81-91`。
- 证据链：spec 的 `datas` 只打包 `config.json / subject.py / app.py / templates`，无 `agent_prompt.json`；`_ensure_config` 首次运行只复制 `config.json` 到 exe 同级；`load_config` 从 `subject_dir`（打包后 = exe 同级）读取 `agent_prompt.json`；`dist/高中物理/` 现有产物确认无该文件。
- 范围修正：当前仓库只有 `specs/高中物理.spec` 一个打包配置和 `dist/高中物理` 一个产物，其余 6 科尚未打包；但 7 个 `main.py` SHA256 逐字节相同、打包模式一致，后续按同样方式打包会逐科复现。
- 影响：打包版 ReAct 模式下 `get_question_prompt()` 的 `config.get("agent_prompt_lines")` 为空，静默回退到普通 `question_prompt_lines`；UI 显示 ReAct 已开启，实际跑的是非代理提示词。
- 建议：spec datas 加入各学科 `agent_prompt.json`，`_ensure_config` 同时复制；启动时检测 ReAct 开启但 agent_prompt 缺失并显式告警。

---

## 二、中危问题（行为与预期不符）

### M1. 讲义（Word）上下标转换在 6 个学科缺失，小学语文反而重复执行

- 位置：`ui/default_app.py:938-1016`、`core/defaults.py:961-995`、`core/pandoc_utils.py`。
- 核实：除小学语文（`subjects/小学语文v3.0/subject.py:81-97`）外，6 个学科没有 `convert_file_to_md`，走 `convert_with_pandoc` 直调；讲义后处理链只做 `fix_latex_escapes → clean → …`，**不调用 `normalize_caret_tilde`**。pandoc 输出的 `^x^` / `~x~` 会原样进入拆分与校对内容。
- 小学语文则通过 `default_convert_file_to_md` 已做一次 normalize + enhance，随后 UI 又执行一次 `enhance_docx_conversion`，重复处理。
- 建议：把“pandoc 转换 → normalize_caret_tilde → 格式增强”收敛为 Base 层唯一默认转换实现；UI 不再重复 enhance。

### M2. “生成 LaTeX PDF”勾选反向控制格式修正开关

- 位置：`ui/default_app.py:1111-1118` → `:1234-1236/:1274-1276` → `core/defaults.py:874-886`。
- `self.generate_pdf` 被直接传成 `default_proofread_one(..., generate_pdf, ...)`；该参数在 defaults 中实际决定“格式不合规时是否启动 LLM bash 修正”。用户取消 LaTeX PDF、只勾 Word 报告时，格式违规将只记日志、不做 LLM 修正。现有测试只锁定“报告落盘与勾选解耦”，未锁定“修正开关被勾选耦合”。
- 建议：新增独立参数（如 `enable_format_fix`），与排版勾选彻底解耦，并补回归测试。

### M3. `SolveEquationTool.domain` 参数完全无效

- 位置：`shared/sympy_tools/tools.py:54-77`、`shared/sympy_tools/templates.py:82-93`。
- 生成代码固定 `solve(eqs, vars, dict=True)`，`domain` 虽传入模板但未参与生成。实测 `domain="real"` 求解 `x**2 + 1 = 0` 仍返回 `[-I, I]`。
- 建议：real 域改用 `solveset` + 实数域过滤，或明确丢弃 `domain` 参数并更新描述；补回归测试。

### M4. 高中历史提示词声明了不存在的 `web_search`

- 位置：`subjects/高中历史v3.0/agent_prompt.json:9` vs `subjects/高中历史v3.0/subject.py:28-36`。
- ReAct 提示词明确告诉模型可用 `web_search`，但 `build_tools()` 只提供 `plan_update / locate_paragraph / read_section`。模型调用会得到 `未知工具: web_search`，被 `_is_empty_or_duplicate` 计为空结果并占空结果熔断配额。全学科交叉核对后，这是唯一的“prompt 声明工具 ∉ 实际工具集”实例。
- 建议：给历史补工具或从 agent_prompt 删除该声明；增加“prompt 声明的工具 ⊆ `build_tools()` 工具名”测试。

### M5. 小学数学 ReAct 复用了物理独立解题实现

- 位置：`subjects/小学数学v3.0/subject.py:32-51`、`57-78`。
- 小学数学导入 `shared.physics_tools.IndependentSolveTool`。修正一处表述：该工具的**对外 description 是通用文案**（难题答案校验），物理痕迹在内部请求 prompt（“请独立求解以下物理题目”，`shared/physics_tools.py:108`）和落盘 `_物理求解.md`（`:171`）。
- 同时，小学数学 `agent_prompt.json` 从未提及 `independent_solve`；`get_tool_instructions()` 又把它归入“可用的符号计算与几何工具”，与实际能力不符。
- 建议：抽象参数化的 `IndependentSolveTool`（subject/落盘名可配）或给数学单独实现；修正工具分类过滤。

### M6. `generate_review_latex` 读取的 JSON 字段与落盘字段不匹配（且生产未接线）

- 位置：`shared/review_latex.py:89-90` vs `core/parsing.py:191-213`。
- 落盘的 `_校对数据.json` 使用 `review_judgments / review_supplements`，而 `generate_review_latex` 读 `judgments / supplements`；即使接线，评审结论恒为空。该模块当前只被 `tests/test_review_latex.py` 引用（且测试用合成 JSON 喂了正确的假键），生产排版统一走 `latex_generator.generate_combined_pdf`。
- 建议：删除，或改为读取真实键并接线；测试改用真实 `save_proofread_json` 产物。

### M7（扩展）. TOOL_LOOP 压缩路径缺主日志；中断路径与日志截断同样违反落盘约定

- 位置：`core/api_client.py:681-708`（TOOL_LOOP）、`:590-598`（INTERRUPTED）、`:356-413`（`_save_conversation_log`）。
- 核实：`empty_streak >= 3` 压缩后只保存 `_API对话记录_full.md`（压缩前），压缩后的最终回复不写主 `_API对话记录.md`（注释自认“与原行为一致”），`default_proofread_one` 的中间产物存档因此缺主日志。
- 本版新增两个相邻缺口：① 工具循环内收到中断信号直接返回，**任何对话日志都不落盘**；② `_save_conversation_log` 本身截断原始内容（用户文本 5000、工具参数 300、工具返回 5000、最终回复 10000 字符），严格说所有路径都不完全满足 AGENTS.md「所有 LLM 原始返回必须落盘」。
- 建议：TOOL_LOOP/INTERRUPTED 路径与 MAX_TURNS 一致补存主日志；评估将截断改为全量落盘或明确“落盘截断上限”约定。

### M8. `_find_md_file` 在 `第N题.md` 与 `第N题_clean.md` 之间非确定选择

- 位置：`shared/latex_generator.py:1292-1296`。
- 取 `os.listdir` 第一个非 `_` 开头 `.md`，`第1题_clean.md` 也匹配。不同平台/文件系统枚举顺序不同，可能把 clean 版当原文生成 PDF。
- 建议：优先精确匹配目录名 `{q_dir.name}.md`（与 `core.defaults.read_md_for_unit` 同语义），找不到再回退；并增加同时存在两文件时必须选原文的回归测试。

### M9. 配置 Schema 元素类型校验缺失，`[123]` 可导致运行时 TypeError

- 位置：`core/config_schema.py:29-34`。
- 只校验 `question_prompt_lines` 是 list，不校验元素是 str；`"\n".join([123])` 必然抛 `TypeError`。另 `knowledge_agent_prompt_lines`（`:36-38`）存在同样的元素类型缺口。
- 另外 `load_config` 缓存键不含 `agent_prompt.json` 的 mtime（`core/config_loader.py:19-38`），运行中编辑 agent_prompt 不会生效。
- 建议：补所有 prompt 数组的元素 str 校验；缓存键加入 agent_prompt mtime。

### M10. 转换中间产物写入源文件目录，而非用户选择的输出目录

- 位置：`ui/default_app.py:938-940`。
- `raw_md` 固定写到 `os.path.dirname(file_path)`，并生成 `{basename}_images/`。用户选择输出目录只影响拆题/校对产物；源目录被 `_raw.md` 和图片目录污染，且源目录只读时转换失败。
- 建议：转换中间产物统一放到输出目录下的临时/转换区，图片引用同步改写。

---

## 三、未实现 / 半落地功能

| 项目 | 位置 | 现状 |
|---|---|---|
| UI 编排服务 | `core/pipeline_service.py:75-134` | ADR-0022 仅交付骨架，`ConversionService/ProofreadService` 直接返回“未搬迁”错误；生产仍走 `ui/default_app._conversion_thread/_proofread_thread`。 |
| Session 中断恢复 | `shared/session.py:136-168`、`ui/default_app.py:1204-1209` | `load_session/find_unfinished/mark_in_progress/get_pending_questions` 只被测试调用；UI 每次新建 session、从不恢复，且运行中不调 `mark_in_progress`（状态只有 pending → completed/failed）。 |
| ADR-0016 标记工具 | `docs/issues/037`、分支 `feat/add-proofread-mark` | `add_proofread_mark / update_proofread_mark` 未合并进 main；ADR 状态写“已实现”但括号注明待合并；主分支实际只有 `EditFileTool`。 |
| `ComputeLimitTool` | `shared/sympy_tools/tools.py:217`、`__init__.py:19-36` | 已实现并导出，但 7 个学科无人接入，用户不可达。 |
| `call_api_continue` | `core/api_client.py:887` | 设计用于旧版 LLM 格式修正；当前格式修正已改 bash 编辑；生产/测试零调用。 |
| `extract_text_start_via_api` | `shared/chinese_classics_tools.py:74` | 定义完整 API 关键词提取流程，但 `preprocess_for_proofread` 实际只用正则，零调用。 |
| `core/paths.py` | README 第 31 行声称存在 | 仓库中不存在；ADR-0022 提到的“safe_name 抽到 core/paths.py”也未落地。 |
| `scripts/test_e2e_agent_pipeline.py` | scripts 目录 | **修正上一版表述**：脚本确实损坏，原因是 `main()` 使用旧 `call_api(api_url=..., api_key=..., model=..., max_loops=..., output_dir=...)` 签名（现签名为 `call_api(ctx, md_text, images, q_title, system_prompt, tools=None)`）；上一版所称“`has_ref` 未定义会 NameError”**不成立**（`build_test_input` 返回的 `has_reference` 在 `main()` 解包为 `has_ref`）。pytest `testpaths=tests` 不收集 scripts，CI 无引用，属实。 |

---

## 四、行为与预期的其他不一致（中低）

1. **批注评审提示词与实际标记格式不符**：`shared/review_mode.py:47-53` 告诉 LLM 标记是 `<批注N>建议</批注N>`，而真实插入格式是 `<批注 id=N><原>…</原><改>…</改></批注>`（`shared/docx_comments.py:70/121/149`），会误导模型理解任务。
2. **评审提示词硬编码语文学科**：`shared/review_mode.py:47/117` 写死“资深语文教研员”，但物理/化学/数学等学科的非 ReAct 评审 prompt 也会拼接这段，学科错位。
3. **`_is_right_column_empty` 忽略 `review_judgments`**：`shared/latex_generator.py:1258-1260` 只检查 comments/numbered/supplements/tool_calls；JSON 只有评审判定时，右栏会提前返回“✅ 校对无问题”，评审结论完全不上栏。
4. **独立解题工具硬编码 `reasoning_effort: high`**：`shared/physics_tools.py:113`、`shared/chemistry_tools.py:191`。若用户配置 `deepseek-chat` 等不支持该参数的模型，主 `call_api` 会自动跳过（`core/api_client.py:752-756`），但独立解题内部请求不会，直接 400。
5. **自由校对接受 BMP 但不发送**：`ui/default_app.py:484/499/501` 允许选择 `.bmp`，`core/defaults.py:808-831` 只编码 `.png/.jpg/.jpeg/.gif`；BMP 会被复制进 `images/`，却永远不会作为图片输入送给模型。
6. **“关闭 ReAct = 传统一次性校对”与实际不符**：README 第 111 行如此描述；但物理/化学/数学非 ReAct 仍保留 sympy + web_search 工具并配 `max_loops=20`，模型仍可多轮工具调用，只是换了一套 prompt。
7. **`default_split_lecture` 的 `do_clean` 参数完全未使用**：`core/defaults.py:332` 签名含 `do_clean`，函数体零引用；7 个学科都在传一个无效参数。
8. **无副作用语句/非确定选择**：`shared/latex_generator.py:1372` 的 `data.get("tool_calls", [])` 无副作用；`_find_md_file` 非确定性见 M8。
9. **IDML 输出为裸文件名时崩溃**：`core/idml_extractor.py:431-432` `os.makedirs(os.path.dirname(output_md_path), exist_ok=True)` 在 `output_md_path="out.md"` 时得到空字符串并抛 `FileNotFoundError`。

---

## 五、冗余与工程卫生

### 1. 明确死代码/无效语句
- `subjects/高中语文v3.0/subject.py:54`：列表推导式结果被丢弃。
- `core/idml_extractor.py:253` `max(y_values)`、`:286` `style.lower()`：两个无副作用表达式（后者疑似“忘记赋值”的潜在逻辑错误，`style` 后续比较是大小写敏感的）。
- `ui/default_app.py:102-103` 与 `core/base_subject.py:105-106`：`show_source_modes / show_exec_modes` **生产 UI 无消费方**（内容类型在 `setup_ui` 硬编码 4 项）；`base_subject.get_ui_features()` 的值目前只被测试消费。
- `ui/default_app.py:420` `setup_extra_options`：空实现且无调用方。
- `ui/default_app.py:775/:778` `on_start_conversion/on_start_proofread`：**修正上一版表述**——它们不是“零调用”（分别在 `:821`、`:1107` 被调用），而是“被调用的空钩子”。
- `ui/default_app.py:51/143` `knowledge_enabled`：`_show_knowledge_option=False`，复选框对所有学科隐藏，变量从未被读取。
- `intent_clean_enabled`：`ui/default_app.py:50` 初始化 True，UI 无对应控件，用户无法关闭“出题意图清理”。
- `shared/latex_generator.py:1263` `generate_tex`、`:1443` `generate_pdf_for_question` 生产零调用；`shared/review_latex.py` 整模块生产零调用。
- `shared/docx_comments.py:168` `extract_comments_to_md`、`core/manual_split.py:158` `split_by_manual_markers`、`shared/split_post_utils.py:15` `remove_navigation_units`、`shared/docx_format_enhancer.py:238` `get_format_marker_list` 等均为仅测试/文档引用的旧入口。
- `shared/sympy_tools/__init__.py:19-36`：`ALL_TOOLS / get_tools_for_langgraph` 零调用；其中 `ComputeLimitTool` 无学科接入。
- `shared/sympy_tools/templates.py:111-126`：`differentiate / integrate` 模板存在，但没有任何工具类暴露。
- `core/base_subject.py:72-82` `generate_knowledge` 保留废弃函数（ADR-0017 决策为保留，可接受但应标注清理时间）。

### 2. 重复
- 7 个 `subjects/*/main.py` 为**逐字节相同**（SHA256 完全一致）；7 个 `app.py` 也几乎全是 `DefaultApp` 空壳。建议抽公共入口 + 学科配置点。
- `physics_tools.py` 与 `chemistry_tools.py` 结构高度相似（`SequenceMatcher` 实测 **78%**，上一版“约 90%”偏高），可抽公共基类。
- `get_question_prompt / get_review_prompt` 的拼接逻辑在 7 个 subject 中有 3 种逐字重复变体。
- 自然排序逻辑在 `ui/default_app.py`（`_natural_key` 与 `_proofread_thread` 内联）、`core/docx_report.py` 三处各自实现。

### 3. 依赖与配置
- `requirements.txt:8` / `requirements.lock:12` 含 `lxml`，Python 源码零引用（IDML 用 `xml.etree`）；**但 `specs/高中物理.spec:81` 的 hiddenimports 明确列了 `'lxml'`**，移除依赖需同步删除 spec 项，否则打包会因 hidden import 缺失告警/失败。
- `pytest.ini` 与 `pyproject.toml` 的 pytest 配置重复，运行时持续告警 `WARNING: ignoring pytest config in pyproject.toml!`。
- `shared/plan_tools.py:3` docstring 含 3 个 U+FFFD 乱码字符。
- `subjects/*/agent_prompt_v*_backup*.json` 等 4 份历史备份、`scripts/_search_results/_prompt_preview_*.md` 生成产物仍被 git 追踪。
- 本地工作区存在被 gitignore 的真实 `.env`（含 API Key），未入库但建议轮换。

### 4. 文档与实现漂移
- `README.md:31` 声称 `core/paths.py` 存在，实际没有。
- `README.md:226-228` 的 `proofread_one(api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf, ...)` 是旧签名；实际为 `(ctx, q_dir, q_name, generate_pdf, source_mode, archive_root)`。
- `README.md:163` 仍描述“五种执行模式”，实际 UI 已改为管线 toggle（ADR-0013）。
- `README.md:144-147` 学科工具数全部过时：实测 ReAct 下物理 11、化学 11、数学 10、语文 4，README 分别写 10/9/7/3。
- `CONTEXT.md:361/411/458` 仍写 ADR-0016/0017/0018 “设计中/待落地”，但同文件第 4 行已写“已落地”，自相矛盾。
- ADR-0004/0005/0006 等状态字段仍为“已接受/已采纳”，未按 AGENTS.md 约定改为“已实现 + commit”。
- `docs/notes/code-review-2026-08-13.md` 的 BashTool **直接** `python -c` 绕过已修复（现有测试锁定）；仍可复现的是**管道/分隔符变体**及本报告新增的换行/命令替换/相对路径穿越。上一版“原复现仍可复现”的表述不准确。pipeline 骨架、session 恢复、README 漂移则确实仍可复现。

---

## 六、测试盲区（测试全绿但仍漏掉的行为）

建议补充以下回归用例。**除标注 ⚠️ 的项外，均已在当前实现下确定会红**：

1. `_validate_bash_command("echo x | python -c ...")` 必须拦截（H1-a）；
2. ⭐新增：`_validate_bash_command("echo x\npython -c ...")`、`echo $(python -c ...)`、`python -m http.server` 必须拦截（H1-b，当前全放行）；
3. ⭐新增：`allowed_dir` 下 `cat ../secret.txt`、`echo x > ../../pwn.txt` 必须拦截（H1-c，当前放行）；
4. `check_equality("x", "-x")` 必须为 false；
5. `solve_equation(domain="real")` 不得返回复数根；
6. 打包资源清单必须包含 `agent_prompt.json` ⚠️（需实际执行 PyInstaller，不能只静态断言）；
7. 讲义转换路径必须把 `v^2^` 转为 `<上标>2</上标>`；
8. 取消 PDF 勾选不得影响格式修正；
9. 每个学科 agent_prompt 声明的工具必须是 `build_tools()` 工具名的子集（当前高中历史红）；
10. `_find_md_file` 在同时存在 `第1题.md` 与 `第1题_clean.md` 时必须选原文 ⚠️（当前实现依赖 `os.listdir` 顺序，测试可能因文件系统顺序偶然绿，应配合确定性构造或先修实现再锁契约）；
11. `review_latex` 必须能读取 `save_proofread_json` 的真实产物；
12. ⭐新增：TOOL_LOOP/INTERRUPTED 路径必须落盘主 `_API对话记录.md`（M7 扩展，当前无测试锁定）。

---

## 七、建议修复顺序

**第一批（安全与正确性）**
- H1（含 1-a/1-b/1-c 全部绕过面）
- H2 等式判等误判
- H3 agent_prompt 打包缺失
- M3 domain 参数失效

**第二批（核心链路一致性）**
- M1 讲义上下标转换收敛
- M2 PDF 勾选与格式修正解耦
- M4 历史 prompt/工具一致
- M7（含中断路径与截断约定）日志落盘闭环
- M9 config schema 元素校验 + agent_prompt 缓存键

**第三批（半落地清理）**
- pipeline_service 完成搬迁或明确下线
- Session 恢复入口接线或删除相关 API
- ADR-0016 分支合并或状态改回“未实现”
- 删除/接线 review_latex、call_api_continue、extract_text_start_via_api 等死代码
- 修复 `scripts/test_e2e_agent_pipeline.py` 签名或移入 tests 并纳入收集

**第四批（工程卫生与文档）**
- 消除 pytest 双配置；移除 lxml（同步修改 spec hiddenimports）
- 统一 main.py/app.py 与 prompt 拼接重复
- 更新 README/AGENTS/CONTEXT/ADR 状态与接口签名
- 清理被追踪的 backup/generated 产物和乱码 docstring

---

### 附：本修订版相对上一版的关键变化

| 类型 | 内容 |
|---|---|
| 修正 | `has_ref` 未定义 → 不成立，脚本仅因 call_api 旧签名损坏 |
| 修正 | `on_start_conversion/on_start_proofread` “零调用” → 实为被调用的空钩子 |
| 修正 | lxml “全仓库零引用” → spec hiddenimports 仍有引用 |
| 修正 | M5 “工具描述为物理” → description 通用，物理痕迹在内部 prompt/落盘名 |
| 修正 | H1 第三条示例 → 生产传 allowed_dir 时被路径检查拦截，换引号内绝对路径可绕过 |
| 修正 | H3 “所有学科打包版” → 当前仅高中物理一个 spec/产物 |
| 修正 | 物理/化学工具相似度 90% → 实测 78% |
| 修正 | 旧审查 BashTool 直接 python -c 绕过 → 已修复，剩余为变体 |
| 修正 | 第六节“均能红” → `_find_md_file` 与打包清单两条不具备确定性 |
| 新增 | H1-b 换行/命令替换/python -m/脚本绕过、H1-c allowed_dir 相对路径穿越 |
| 新增 | M7 扩展：INTERRUPTED 不落盘、日志截断与 AGENTS.md 冲突 |
| 新增 | 测试盲区 2/3/12 三条回归建议 |
