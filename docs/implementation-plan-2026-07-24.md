# 实施方案：架构优化落地总览（2026-07-24）

> 全部 grill 决策汇总：7 份 ADR（0021~0027）+ 1 份 Issue（048）。
> 基调：**纯优化、零功能变更**。各 ADR 经 2026-07-24 审查均已加"严格保留原差异 / log 输出逐字不变 / 对外接口字段面冻结"等约束，避免抽取式重构无意中改行为。
> 施工原则：每条 ADR 独立支线；除 ADR-0021 的 C1+C2+C3 必须原子落地外，其余各支线内部可分多个小 commit。

---

## 一、支线总览与落地优先级

| 优先级 | 支线 | 标题 | 复杂度 | 依赖 | 风险 |
|---|---|---|---|---|---|
| **P0** | Issue 048 | 仓库清理 + ADR 状态同步 + 流程约定写入 AGENTS.md | 低 | 无 | 几乎零 |
| **P0** | ADR-0027 | 工程化基线 + 集成测试复位 | 中 | 建议 Issue 048 后 | 中（首次 ruff 会暴露大量既有违规） |
| **P0** | ADR-0021 | call_api 重构 + 退化测试修复 + 散落超时常量上提 | 高 | 建议 ADR-0027 后（ruff 已守护） | 中（call_api 是核心路径） |
| **P1** | ADR-0025 | pdf_compiler 拆四函数 + 诊断去重 | 中 | 独立 | 中（编译路径，端到端依赖 latex 环境） |
| **P1** | ADR-0024 | latex_generator pipeline 化 + 内部去重 | 中 | 独立 | 高（最易踩"无意中改行为"的雷） |
| **P1** | ADR-0022 | UI 编排下沉到 core | 高 | 建议 ADR-0021 后（service 依赖 `call_api` 稳定） | 高（3100 行 UI 中 ~433 行业务搬走） |
| **P1** | ADR-0023 | 物理/化学跨模块凭证设置去重 + 缓存锁 + env 读改写 | 中 | 独立 | 低（保留薄包装、单点改造） |
| **P2** | ADR-0026 | 化学式解析双源同步测试锁 | 低 | 独立 | 低（运行时零变更） |

### 推荐先做这三条
1. **Issue 048** — 立即把 untracked 的 ADR-0019/0020 + Issue 039-047 `git add`、删测试残留物、补 `.gitignore`，先给后面的施工干净的工作树
2. **ADR-0027** — ruff/pre-commit/锁文件/pyproject 铺好，后续每个 ADR 落地都有"门闸"
3. **ADR-0021** — 本支线主菜，解决 call_api 单函数 375 行的核心债务

---

## 二、施工简报（每支线一份）

### Issue 048：清理 + 流程约定

**改动文件清单**：
- 删 `_smart_split_raw_attempt1.md`、`_smart_split_raw_attempt2.md`
- 修改 `.gitignore`（加 `.DS_Store`、`/.kilo/`、`.pytest_cache/`、`.zcode/`、`tests/_search_results/`、`_smart_split_raw*.md`）
- 修改 `CLAUDE.md`、`Trae.md`（合并入 AGENTS.md 或迁 `docs/`，留一份单点维护）
- 修改 `AGENTS.md`（加 I1/I2/I3 三条流程约束）
- 修改 `memory/MEMORY.md`（沉淀 ADR 索引）
- 移动 `create_issues.py` → `tools/create_issues.py`
- 移动 `docs/_all_prommts_full.md` / `docs/prompt_summary.md` → `docs/notes/`
- `git add docs/adr docs/issues` 并补一次"文档同步"提交
- 修改 `README.md`（补高中历史学科一行；标题"v3.0"说明；项目结构树同步实际 core/ 模块）

**实施步骤**：
1. 删两个测试残留 md + 补 `.gitignore`
2. 把 `docs/adr/0019-*.md` / `0020-*.md` 与 `docs/issues/039~047` 一起 git add、补一次提交
3. merge CLAUDE.md/Trae.md 入 AGENTS.md，删两份冗余文件
4. 修订 README 学科表 + 项目结构树
5. AGENTS.md 加三段流程约束
6. `MEMORY.md` 沉淀为 ADR 索引表

**完成判定**：`git status` 干净；ADR-0016/0017/0018 状态字段已改"已实现（commit XXX）"；README 学科表 7 行；`.gitignore` 能让 `git status` 不再出现 `.DS_Store`、`.kilo/`。

**风险点**：删除 `CLAUDE.md` / `Trae.md` 前确认无误读历史决策依赖；merge 时人工读对照，不要漏内容。

---

### ADR-0027：工程化基线 + 集成测试复位

**改动文件清单**：
- 新增 `pyproject.toml`（ruff 配置 + 包元信息 + python_requires）
- 新增 `requirements.lock`（或 `uv.lock`）+ 修改 `requirements.txt` 补 Pillow、lxml、playwright
- 新增 `.pre-commit-config.yaml`（ruff check + ruff format --check）
- 修改 `.github/workflows/*.yml`：删 `|| true`、删不存在的 `test_e2e_knowledge.py`、加 windows-latest、用 `-m "not e2e and not network and not slow"`
- 修改 `pytest.ini`：删 `--ignore`、在 `addopts` 里加 `-m "not e2e and not network and not slow"`
- 修改原 5 个 `--ignore` 测试文件：加 `@pytest.mark.e2e / network / slow` markers
- 移动 `tests/test_e2e_agent_pipeline.py` → `scripts/`
- 移动 `tests/diagnose_diff_paths.py`、`tests/preview_react_prompt.py`、`tests/_search_results/` → `scripts/`
- 顺手清理 ruff 标红的"最小违规"（单 import 同行、未使用 import 等）

**实施步骤**（参考 ADR-0027 的实施顺序约束）：
1. C1+C2 同 PR：建 `pyproject.toml` + ruff 配；生成锁文件，补漏列依赖；CI 去 `|| true`
2. ruff 跑一次既有代码，清理最小违规（单 import、未使用 `re` 等）
3. C3 markers + addopts：删 `--ignore`、5 文件加 marker、pytest.ini 加默认 `-m` 排除
4. C4 双平台 CI matrix（ubuntu + windows，Python 3.12）
5. C5 `test_e2e_agent_pipeline.py` 迁 scripts/

**完成判定**：
- `pre-commit run --all-files` 全绿
- `pytest`（无参数）跑的文件集合与现状一致
- `pytest -m e2e` 能跑起原被忽略的集成测试（手动验证）
- CI 两条流水线（ubuntu+windows）均绿
- windows CI 跑起 tkinter 导入不崩

**风险点**：ruff 首次跑可能暴露几十处违规——只清理"最小违规"，复杂违规（长函数）留给后续 ADR；不要为了 ruff 全绿改大块代码。

---

### ADR-0021：call_api 重构 + 退化测试修复 + 散落超时常量上提

**改动文件清单**：
- 修改 `core/api_client.py`：
  - 新增 `LoopResult` dataclass（C2）
  - 新增 `_post_chat()` / `_run_tool_loop()` / `_handle_retry()` / `_build_error_report()`（C1）
  - 合并 `_save_conversation_log` 与 `_save_conversation_log_full` 为 `_save_conversation_log(..., suffix="")`（C3）
  - `call_api` 主函数降到 ~80 行编排
  - `call_api` 返回 6 key dict 逐字不变、`call_api_continue` 2 key 不变
  - `_save_conversation_log_full` 的 `except: pass` 同时修复（落 `log(完整 traceback)`）
- 修改 `shared/bash_tool.py`：`timeout=30` 提为模块级 `BASH_TIMEOUT = 30`（**数值不变**）
- 抽 `shared/docx_format_enhancer.generate_clean_md(md_text, repl)` 公共函数
- 修改 `core/base_subject.py:214-221` 改调 `generate_clean_md(new_content, self._clean_bold_replacement)`
- 修改 `tests/test_clean_md_pipeline.py`：
  - 删本地 `make_clean_md`，改 import 真实 `generate_clean_md`
  - 参数化 fixture 跑两套 `repl`: `"\x01"` 与 `r"\1"`
  - 既有断言全部保留，对两套 repl 各跑一遍

**实施步骤（严格按 ADR-0021 实施顺序约束）**：
1. C2 先行：写 `LoopResult` dataclass，字段面冻结
2. C1 抽 4 函数：先把 `_post_chat` 薄函数抽出（消除 4 处重复 post 样板），所有调用点改调；再抽 `_run_tool_loop`（4 退出路径走 `LoopResult`，循环体内 `return` 改 `stop_reason + break`）；再抽 `_handle_retry`、`_build_error_report`
3. `call_api` 主函数重写为编排：构造 payload → `_post_chat` → `_run_tool_loop` → 落盘 → 返回
4. C3 合并两个 save_log 函数；`_full` 的 except 同时修
5. C5 `generate_clean_md` 抽取 + base_subject 改造 + test 改造（独立可先行）
6. C4 BashTool 仅提 `BASH_TIMEOUT` 常量

**完成判定**：
- 现有 `tests/` 全绿（特别是 `test_default_proofread_one`、`test_comprehensive_clean`、`test_format_enforcement` 等涉及 call_api 的）
- 新增 `tests/test_call_api_refactor.py`：mock choice 序列覆盖 4 条退出路径的 stop_reason
- `test_clean_md_pipeline` 两套 repl 各跑通过
- `core/api_client.py` 主函数从 ~375 行降到 ~80 行
- BashTool `_run` 体内 `timeout=` 改为 `BASH_TIMEOUT`，行为零变化

**风险点**：
- call_api 是最高危路径，重构前先保证全 test 套件绿；重构期允许临时保留旧函数名以便回退
- `LoopResult` 字段建议用 frozen dataclass + `as_dict()` 返回原 6 key；dict 字段名、顺序严格对齐
- `_save_conversation_log` 合并前必须仔细比对两个原函数除文件名 + except 外有无其它差异（已比对：仅这两点差异）

---

### ADR-0025：pdf_compiler 拆四函数

**改动文件清单**：
- 修改 `shared/pdf_compiler.py`：
  - 抽 `_build_compile_env(texmf_root, tmpdir, fonts_tmp) -> dict | None`（texmf_root 为 None 返回 None）
  - 抽 `_run_xelatex(cmd, log_path) -> tuple[int, str]`
  - 抽 `_run_xdvipdfmx(...)`（与 `_run_xelatex` 同构）
  - 抽 `_diagnose_log(log_path) -> str`、`_format_compile_error(stage, retcode, diagnostic) -> str`
  - `compile_to_pdf` 主函数降到 ~50 行编排
  - `timeout=120`（248、317 两处）提为 `LATEX_COMPILE_TIMEOUT = 120`（数值不变）
- 修改相应 `compile_to_pdf` 调用点（grep 检查仅一处）

**实施步骤**：
1. C2 提常量：`LATEX_COMPILE_TIMEOUT = 120`，两处 `timeout=120` 改 `LATEX_COMPILE_TIMEOUT`（零风险先行）
2. C1 按顺序抽：`_build_compile_env` → `_diagnose_log` / `_format_compile_error` → `_run_xelatex` / `_run_xdvipdfmx`
3. 主函数重写为编排
4. 每抽一步跑一次 `test_math_pdf`（如本机装 xelatex）确认无回归

**完成判定**：
- 主函数从 ~220 行降到 ~50 行
- env vars 字段面与现状逐字一致（含 `;` `!!` 路径拼接）
- texmf_root 为 None 时 `compile_kwargs` 不含 `env` key
- 诊断两处的最终 `RuntimeError` 文本逐字不变
- 本机若装 xelatex，`test_math_pdf` 跑过；没装则环境 skip 守卫（ADR-0019 C6.4 已加）

**风险点**：
- subprocess 调用细节（`subprocess.call` vs `run`、`cwd`、`stdout=DEVNULL`、Windows `CREATE_NO_WINDOW`/`STARTUPINFO`）全部严格保留
- mock subprocess 单测仅断言调用参数，不真跑 xelatex；CI 不依赖 latex 装机

---

### ADR-0024：latex_generator pipeline 化 + 内部去重

**改动文件清单**：
- 修改 `shared/latex_generator.py`：
  - 新增 `_RenderState` dataclass（C1）
  - 抽 `_PIPELINE = [(name, fn), ...]` 步骤列表
  - `build_paracol_content` 改为循环调用 pipeline
  - 抽 `_wrap_corrmark_math(num, inner, open_d, close_d, in_math, with_dollar_guard)`——**严格保留四分支原差异**（C2）
  - 抽 `_consume_braced_superscript(text, i, marker_cmd)`（C3）
  - 提模块级 `_BOLD_RE` / `_ITALIC_RE`（三处改 import）
  - `_get_section_name` 7 字符转义表拆"全文转义表 vs 文件名转义子集"（保留差异）
  - 抽 `_FALLBACK_SYMBOLS` 单一常量驱动 replace 与 `_keep`
  - `_UNICODE_MATH_MAP` 与 `_MATH_ONLY_RE` 从单源映射派生
  - **严守**：log 输出文本逐字不变；既有端到端测试不动
- 新增 `shared/comment_marker.py`：抽三条注释性正则/构造/解析函数（C5）
- 修改 `shared/docx_comments.py`、`shared/latex_generator.py:238/1028` 改 import comment_marker
- 提模块级 `_INLINE_MARKER_RE`（`core/parsing.py:157/162/170`、`core/format_enforcement.py:36` 四处改 import）
- 新增 `tests/test_latex_pipeline_steps.py`：每步独立单测

**实施步骤（严格按 ADR-0024 顺序约束）**：
1. C5 批注标记统一 / 内联 marker 正则——最先做（独立、低风险、铺路）
2. C4 重复正则与表去重——机械抽取
3. C1 pipeline 化：先定 `_RenderState` 字段清单（最易欠设计）→ 拆步骤 → 主函数循环调用；保留既端到端测试作网
4. C2 + C3 在 C1 稳定后做（这两块是 pipeline 内部的分支抽离）
5. **明确不做**：「C2 补 `'$' in inner` 兜底」已被 ADR 剥离为独立 bug 修复 issue，不在本支线

**完成判定**：
- `build_paracol_content` 主函数从 ~205 行降到 ~10 行（仅循环 pipeline）
- 每步独立单测覆盖
- 既有 `test_build_paracol` / 数学相关测试全绿
- 三处批注标记三套差异分别保留，使用点 zero behavior change
- 粗/斜体正则合并后字面与现状逐字一致

**风险点**（本 ADR 最低估）：
- `_RenderState` 字段设计预留充分时间——字段不齐会让步骤间传递隐式状态
- 端到端测试做回归网；严禁"拆完即删端到端测试"
- 三处批注语义不同（注释全匹配 vs 含原改子字段 vs 补全标签），不强统一字面

---

### ADR-0022：UI 编排下沉到 core

**改动文件清单**：
- 新增 `core/pipeline_service.py`：
  - `ConversionService` 类，`run_conversion(req: ConversionRequest) -> ConversionResult`
  - `ProofreadService` 类，`run_proofread(req: ProofreadRequest) -> ProofreadResult`
  - 构造期接收 `on_progress` / `on_log` 回调（**回调签名约束为纯数据参数，service 不知道 tk**）
  - 构造期接收单个 `threading.Event` 作中断源
- 新增 `core/unit_detect.py`：`is_unit_dir(d: Path) -> bool`、`scan_question_dirs(root) -> list[Path]`
- 修改 `core/defaults.py`：`_is_unit_dir` 改 import unit_detect
- 修改 `ui/default_app.py`：
  - `_conversion_thread` 内容下沉到 `ConversionService`
  - `_proofread_thread` 内容下沉到 `ProofreadService`
  - UI 线程启动器改"创建 req + 调 service.run_*"
  - `select_pdf_folders`(672) 与 `_proofread_thread:1075-1083` 两处目录识别正则改调 `unit_detect.is_unit_dir`
  - `_export_paper_report` / `safe_name` 纯逻辑抽到 `core/paths.py` 或留在 service
  - **保留 `task_interrupt` bool 作 mirror** 不强行删
- 新增 `tests/test_pipeline_service.py`、`tests/test_unit_detect.py`

**实施步骤**：
1. 先抽 `core/unit_detect.py` 并改两处 UI/proofread 的目录识别（小溯源切，可独立验证）
2. 设计 `ConversionRequest` / `ConversionResult` / `ProofreadRequest` / `ProofreadResult` 数据类（与原 thread 状态字段一一对应）
3. 抽 `ConversionService` → 单线程验证 `run_conversion`
4. 抽 `ProofreadService` → 单线程验证 `run_proofread`
5. UI 线程启动器改调 service；保留中断 bool 作 mirror
6. 补 service 单测（缓存命中、未命中、partial、中断、batch_size 解析）

**完成判定**：
- `ui/default_app.py` 从 ~1260 行降到 ~700 行
- `core/pipeline_service.py` 全模块可单测，无 tk 依赖
- `core/unit_detect.is_unit_dir` 单一源，UI 与 proofread 共用
- 既有 UI 行为（用户操作、输出文件结构）人工跑一遍不出现回归
- 中断行为人工验证：UI 点"停止"，service 看到中断后立即 return

**风险点**：
- UI 改写面积不小，必用一次独立 commit 完整切换，不做夹生过渡
- `on_progress`/`on_log` 回调若夹带 tk Widget 引用即 service 重新耦合 UI —— ADR 已写明纪律，code review 时严查
- 保留 `task_interrupt` bool 是有意为之，未来若要清理是另一条支线

---

### ADR-0023：物理/化学跨模块凭证设置去重 + 缓存锁 + env 读改写

**改动文件清单**：
- 新增 `shared/_subject_api_config.py`：`set_subject_api_config()` / `get_subject_api_config()` 单一实现
- 修改 `shared/physics_tools.py` + `shared/chemistry_tools.py`：
  - 保留 `set_physics_api_config` / `set_chemistry_api_config` 作薄包装（签名、参数顺序逐字一致）
  - 私有 `_api_config` / `_get_api_config` 改调跨模块共享
  - **不删 threading.local**、**不改工具 `__init__`**、**不改 build_tools 时机**、**不动 defaults.py:832-838**
- 修改 `core/session_context.py`：`from_credentials` 默认 `max_loops` 改 20（与 dataclass 一致）
- 修改 `core/config_loader.py`：
  - 加 `threading.Lock`
  - `_config_cache` key 升级为 `(subject_dir, mtime_tuple)`
- 修改 `core/env_config.py:save_env_config`：从"覆写三键"改为"读改写保留额外键与注释"

**实施步骤**：
1. C4 env_config 读改写——独立可先行
2. C2 `from_credentials` 默认值改 20（独立、零影响调用方）
3. C3 config_loader 加锁 + mtime（独立）
4. C1 抽 `shared/_subject_api_config.py`，physics_tools/chemistry_tools 改薄包装（**保留旧函数名作接口表面**）

**完成判定**：
- `set_physics_api_config` / `set_chemistry_api_config` 函数名仍存在，`defaults.py:832-838` 调用零改动
- 工具 `__init__` 仍无参实例化（7 学科 build_tools 不动）
- `set_subject_api_config` 单一源；两个旧函数作薄包装
- `load_config` 并发安全、mtime 变更后自动失效
- env_config 保存：`.env` 仅含三键无注释时，输出与原行为逐字一致；含额外键时保留之
- `test_chemistry_balance` / `test_physics_*` 全绿

**风险点**：
- 保留薄包装是本 ADR 的特意约束——不要为"更干净"删除旧函数名
- 薄包装的参数顺序必须与原函数完全一致（`api_url, api_key, model, output_dir=None`）

---

### ADR-0026：化学式解析双源同步测试锁

**改动文件清单**：
- 抽 `_MOLAR_MASSES` 到 `shared/chemistry_tools.py` 模块级常量
- 修改 `shared/sympy_tools/tools.py:362-388`：删本模块字面量字典，改 import
- 修改 `shared/sympy_tools/templates.py`：模板内 `molar_masses` 参数来源不变（仅改 import 点）
- 新增 `tests/test_chem_formula_sync.py`：开发模式跑，断言主源与沙箱内嵌字面量结构逐字一致
- **templates.py 内嵌的 `_PARSE_FORMULA_SRC` / `_parse_formula` 字符串字面量不动**（保现状）

**实施步骤**：
1. 全仓 grep `_MOLAR_MASSES`：确认调用点（仅 `tools.py` / `templates.py`）；抽到 `chemistry_tools.py`；两处改 import
2. 写 `test_chem_formula_sync.py` 测试锁
3. 跑 `test_chemistry_balance.py` 全绿
4. 手动比对一次当前 templates.py 内嵌 `_parse_formula` 字面量 vs `chemistry_tools.parse_chemical_formula` 源码——确认当前是否已漂移；若有漂移已在历史时点修正后再走本测试锁

**完成判定**：
- `_MOLAR_MASSES` 单一源
- templates.py `_PARSE_FORMULA_SRC` 字面量与现状逐字相同（运行时行为零变化）
- `test_chem_formula_sync.py` 通过
- `test_chemistry_balance.py` 通过

**风险点**：
- 测试锁依赖开发模式有源码；打包测试环境不在覆盖范围（可接受）
- 抽 `_MOLAR_MASSES` 全仓 import 点清零，防漏

---

## 三、跨支线纪律

以下原则贯穿全部 7 条支线，落地时无需每条 ADR 重复——本方案层级的总纪律：

1. **零功能变更**：每条支线的 PR 描述都要回答一句"本支线无功能行为变更"，并指出回归测试如何保证
2. **严格保留原差异**：抽公共函数/常量去重时，字面量逐字相同才合并；不同处一律保留差异
3. **`log()` 输出文本逐字不变**：UI 日志面板用户可见文本（emoji、缩进、截断长度）与现状一致
4. **对外接口字段面冻结**：`call_api` 返回 6 key、`call_api_continue` 返回 2 key、`set_*_api_config` 签名、`generate_clean_md` 接收 repl 参数——全部逐字不变
5. **既有测试是回归网**：抽函数期间严禁删既有测试；新增单测与抽函数同步交付
6. **每条支线单独 PR**：除 ADR-0021 的 C1+C2+C3 必须原子落地外，支线内可分多个小 commit，便于 review 回溯
7. **ruff 守护**：ADR-0027 落地后，后续每条支线提交前必跑 `ruff check` + `pre-commit run`；既有违规不留给后续 ADR 顺手清，由 ADR-0027 阶段集中处理"最小违规"

---

## 四、Issue 拆分建议

按 AGENTS.md 工作流「Issue/ADR 与代码同 PR 提交」，每条支线对应一组 Issue 落 docs/issues/：

| Issue 编号 | 标题 | 对应 ADR |
|---|---|---|
| 049 | 仓库清理 + 流程约束写入 AGENTS.md | Issue 048 |
| 050 | 工程化基线：ruff + pre-commit + pyproject + 锁文件 | ADR-0027 C1 |
| 051 | 集成测试复位：markers 取代 --ignore + 双平台 CI | ADR-0027 C3+C4+C5 |
| 052 | call_api 重构拆 4 函数 + LoopResult | ADR-0021 C1+C2 |
| 053 | _save_conversation_log 合并去重 + except 扫尾 | ADR-0021 C3（同时承接 ADR-0019 C1.3 散尾） |
| 054 | test_clean_md_pipeline 改 import generate_clean_md + 抽公共函数 | ADR-0021 C5 |
| 055 | BashTool 超时常量上提 | ADR-0021 C4 |
| 056 | pdf_compiler 拆四函数 + 诊断去重 | ADR-0025 |
| 057 | latex_generator pipeline 化 + 内部去重 | ADR-0024 |
| 058 | UI 编排下沉到 core（ConversionService + ProofreadService） | ADR-0022 |
| 059 | 物理/化学跨模块凭证设置去重 | ADR-0023 C1 |
| 060 | from_credentials 默认值对齐 + config_loader 缓存加锁 + env 读改写 | ADR-0023 C2+C3+C4 |
| 061 | 化学式解析双源同步测试锁 + _MOLAR_MASSES 单一源 | ADR-0026 |
| 062（独立） | BashTool 安全加固（路径白名单 + 命令黑名单 + 绕过测试） | 独立安全议题（被 ADR-0021 C4 剥离而来） |
| 063（独立） | `_process_inline_markers` 补 `'$' in inner` 兜底（先行验证是否 bug） | 独立 bug 修复（被 ADR-0024 C2 剥离而来） |

**待落地优先级**：049 → 050 → 052+053→051 → 054 → 056 → 057 → 058 → 060 → 059 → 061 → 055 → 062/063（独立）

---

## 五、整体里程碑预估

| 里程碑 | 涵盖支线 | 收益 |
|---|---|---|
| M1（清理 + 工程化） | Issue 048 + ADR-0027 | 仓库整洁、ruff 守护、CI 真 平台运行 |
| M2（核心重构） | ADR-0021 | call_api 主路径可单测、回归网建好 |
| M3（PDF/LaTeX 重构） | ADR-0025 + ADR-0024 | 两大文本处理函数可单测 |
| M4（UI 下沉 + 配置优化） | ADR-0022 + ADR-0023 | UI 业务零测试解决、配置路径清晰化 |
| M5（去重收尾） | ADR-0026 | 化学设计双份同步 |

各里程碑之间彼此解耦；M1 是其它所有里程碑的"门闸"——有了 ruff + pre-commit + CI 才能后续每个 PR 都被守护。