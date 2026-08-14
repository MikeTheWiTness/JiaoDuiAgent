# 代码审查汇总（2026-08-13）

> 审查方式：主代理通读 core/、ui/、工程配置 + 3 个并行审查代理逐行深读 shared/（24 文件）、core/+ui/（15 文件）、学科层/测试/工程配置。
> 关键疑点已用脚本复现验证（见附录 B）。审查全程只读，未修改任何代码。

## 审查概况

| 项目 | 状态 |
|---|---|
| 测试 | 851 passed / 0 skipped / 41 deselected（e2e/network/slow 标记） |
| lint | 392 个 ruff 问题（168 E501、59 W605、35 F541、32 E702、23 E741 等；`--fix` 可自动修 115 个） |
| 护栏 | 学科接口一致性、提示词质量、bug 回归锁测试扎实；无 P0 接口漂移 |
| 结论 | 无必然崩溃的 P0；P1 × 7、P2 × 29、P3 × 30+ |

**总体评价**：架构清晰、ADR 驱动、`core/` 无学科特定逻辑（ADR-0011/0012 下沉已落地）。优化空间集中在三类：**半落地的重构**（pipeline_service 骨架、session 恢复、spec 打包配置）、**UI 层状态管理**、**工程卫生**（lint 债、依赖漂移、文档同步）。

---

## 决策更新：LaTeX 排版功能将下线（仅保留 Word 排版）

> 后续修复中，LaTeX/PDF 编译链路相关问题**不再修复**（相关文件未来随功能下线删除）。标注 ❌ 的条目取消：
>
> - **P1（已修复，功能将下线）**：P1-4 的 `shared/pdf_compiler.py` 部分、P1-5
> - **P2（取消）**：D1、D2、F4
> - **P3（取消）**：死代码 `shared/latex_generator.py:341-343`、风格 `shared/review_latex.py:58`；lint 债中 `tests/test_fix_latex_escapes.py` / `shared/latex_generator.py` / `tests/test_math_pdf.py` / `tools/build_minimal_texlive.py` 随文件下线一并取消
>
> Word 排版链路（`core/docx_report.py`、`shared/formula_render.py`、`shared/comment_marker.py`）保留，相关问题（B1/B2、D5、P1-6/P1-7 等）照常修复。

---

## 一、P1 级问题（7 条，建议第一批修复）

### P1-1 UI 任务状态恢复无 finally 兜底 → 按钮永久置灰、应用卡死
**位置**：`ui/default_app.py:813-1060`（`_conversion_thread`）、`:727-761`（`start_generate_pdf._run`）、`:1062-1068`（`start_proofread`）
**问题**（3 条触发路径）：
1. **确定性复现**：未配置 API 直接跑「完整流程」→ 转换成功 → `root.after(500, self.start_proofread)`（行 1055）→ `start_proofread` 检测到 API 缺失 → 弹窗后 `return`（行 1066-1068），而按钮恢复只在转换线程的 `else` 分支 → `btn_action` 永久 DISABLED，只能重启
2. `_conversion_thread` 整函数无 try/finally：后处理链（`fix_latex_escapes`/`clean_md_file` 等）任一抛异常 → 线程静默死亡 → 按钮无人恢复
3. 运行期间右键删除清单项（`_delete_selected_from_list` 无 `task_running` 防护）→ 迭代中 `proofread_list` 被改 → RuntimeError → 按钮卡死
**附带问题**：`start_conversion` 不置 `task_running=True`，转换阶段「中断」按钮不可用、`interrupt_task` 静默无效
**建议**：三个入口统一「线程体 try/finally，finally 中 `root.after(0, ...)` 恢复按钮 + 复位状态」；`start_proofread` 早退分支也恢复按钮；`start_conversion` 置 `task_running` 并启用 `btn_stop`；列表变更方法加运行中防护

### P1-2 安全：BashTool 沙箱可被 `python -c` 任意绕过（已复现）
**位置**：`shared/bash_tool.py:44-82`；生产调用方 `core/format_enforcement.py:145`
**问题**：白名单只检查第一个命令名（`python` 在白名单），危险模式与 `allowed_dir` 路径检查都跳过 `python -c "..."` 内部字符串（行 76 注释自认"不做静态分析"），而 description 主动推荐 `python -c`。复现结果：
- `python -c "import shutil; shutil.rmtree('/tmp/xxx')"` → 放行
- `python -c "import os; print(open('/etc/hosts').read())"` → 放行
- 对照：`cat /etc/passwd`、`rm -rf /tmp/xxx` → 正确拦截
**建议**：对 `python -c` 代码参数复用 `shared/sympy_tools/safety.py` 的静态扫描；或从白名单推荐文案移除 `python -c`（已有 read_file/write_file 专用工具，`python -c` 非必需）

### P1-3 安全：EditFileTool 无任何路径校验
**位置**：`shared/bash_tool.py:154-227`
**问题**：FileReadTool/FileWriteTool 均有 `allowed_dir` 字段并调 `_validate_file_path`，EditFileTool 两者皆无，`open(path, "w")` 直写任意路径。`tests/test_bash_security.py:116-117` 注释证实是「修复 read/write 漏掉 edit」的遗留。当前无生产调用方（仅测试实例化），但一旦学科接线即绕过沙箱
**建议**：补 `allowed_dir` 字段 + 复用 `_validate_file_path`，加 `..` 穿越回归测试

### P1-4 资源泄漏：subprocess 超时不杀子进程（已复现）
**位置**：`shared/pdf_compiler.py:288/330`（`_run_xelatex`/`_run_xdvipdfmx`）、`shared/sympy_tools/sandbox.py:35`
**问题**：`subprocess.run(timeout=...)` 抛 `TimeoutExpired` 时不会终止子进程（已用 `sleep 5, timeout=1` 复现：异常抛出后进程继续存活）。xelatex 120s / sympy 30s 超时后后台残留进程持续占 CPU 并可能写出半成品
**建议**：改用 `subprocess.Popen` + `communicate(timeout=...)`（超时自动 kill），或捕获 `TimeoutExpired` 后显式 `proc.kill()`

### P1-5 功能错误：`marked_text` 换行还原破坏 LaTeX 命令（已复现）
**位置**：`shared/latex_generator.py:1348`
**问题**：`marked_text.replace('\\n', '\n')` 会把 `\newline`、`\noindent` 等命令中的字面 `\n` 一并替换为换行（已复现：`\noindent` → 换行 + `oindent`），生成损坏 .tex。触发条件：marked_text 同时含字面 `\n` 序列与 `\n` 前缀 LaTeX 命令
**建议**：改用 `re.sub(r'(?<!\\)\\n(?!\w)', '\n', text)`，只匹配独立 `\n` 序列

### P1-6 打包产物启动即崩溃：spec 排除 matplotlib 但导入链必达
**位置**：`specs/高中物理.spec:82`（`excludes=[...,'matplotlib',...]`）；导入链 `ui/default_app.py:26` → `core/docx_report.py:24` → `shared/formula_render.py:16`（顶层 `import matplotlib`）
**问题**：全部学科 GUI 继承 `DefaultApp`，按 packaging.md 用该 spec 打包后，任何学科启动即 `ModuleNotFoundError: matplotlib`。未提交的 `formula_render.py` 已进主线，spec 未同步
**建议**：从 excludes 移除 matplotlib（或 formula_render 内 try/except 降级），hiddenimports 补 `shared.formula_render`、`core.docx_report` 等

### P1-7 依赖锁漂移：requirements.lock 缺 matplotlib，CI 掩盖
**位置**：`requirements.txt:10`（`matplotlib>=3.8`，未提交修改）；`requirements.lock`（7-24 生成，无 matplotlib）；`.github/workflows/test.yml:49`（CI 用 lock 安装）
**问题**：CI 不装 matplotlib，`tests/test_docx_report.py:444` 用 `except ImportError → SkipTest` 静默掩盖 → CI 全绿但公式渲染从未被真正测试、打包必挂
**建议**：更新 lock 纳入 matplotlib；CI 增加「lock 与 requirements.txt 同步」校验步骤（防再漂移）

---

## 二、P2 级问题（按主题分组）

### A. 架构收尾（半落地的重构）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| A1 | `core/pipeline_service.py:78-142` | ADR-0022 C2 搬迁未完成：`ConversionService.run_conversion` 对不存在的文件返回 `success=True` 且零工作（静默假成功）；`ProofreadService.run_proofread` 返回 `completed=total` 而未实际校对 | 完成搬迁（推荐），或骨架改为显式报错防误接线 |
| A2 | `shared/session.py` + `ui/default_app.py` | Session 持久化「只写不读」：`find_unfinished`/`load_session`/`mark_in_progress` 只有测试调用，中断恢复功能未落地，sessions 文件只增不减 | 补恢复入口或明确砍掉；`_save` 固定 `.tmp` 文件名 + 无锁，并发写会交错损坏 |
| A3 | `ui/default_app.py:813-1060` | 转换阶段不可中断：0 处 `task_interrupt` 检查（校对线程有 7 处），批量转换 + 智能分割（LLM 调用）时只能等或杀进程 | 循环体加中断检查 + 置 `task_running`（并入 P1-1 修复） |
| A4 | `ui/default_app.py:377-406` | 管线组合校验不全：导入关 + 拆分开 + 排版开时排版阶段被静默丢弃，无任何提示 | 补组合校验或按 `active_stages()` 精确路由并提示 |

### B. 数据正确性

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| B1 | `core/parsing.py:96` vs `core/docx_report.py:27` vs `shared/comment_marker.py:24` | 跨行标记解析不一致：docx `_PAT` 带 DOTALL，parsing 与 `INLINE_MARKER_DETECT_RE` 不带 → 同一份 LLM 输出 Word 报告能提取批注而 `_校对数据.json` 丢失该条；`_enforce_format` 误报触发无谓 bash 修正；另编号降序区间（⑮-⑫）静默丢原因 | 统一为带 DOTALL + `\\\|` 转义处理的单一捕获正则（放 comment_marker 作唯一源），三处引用 |
| B2 | `core/docx_report.py:447-472` | 标题含 XML 特殊字符（`&`/`<`/引号）时 `re.escape(title)` 匹配不到 w:t 内转义文本 → 该单元「无问题」批注被静默清掉；正文若有同名标题会重复注入锚点 | 用 `xml.sax.saxutils.escape` 构造匹配串；匹配不到时 log 告警；`sub` 前计数告警 |
| B3 | `ui/default_app.py:1120-1128` vs `core/unit_detect.py:8` | 目录识别三处规则漂移：UI 用 `"题" in item`（「错题集」「试题分类」被当校对单元，实测 5 类目录分歧），core 要求前缀锚定 `^(第\d+题\|板块\d+\|单元\d+)`；行 707 又是第三份正则 | 统一调用 `core.unit_detect` 的 `is_unit_dir`/`scan_question_dirs`，删除 UI 内联扫描 |
| B4 | `core/config_schema.py:29-33` | `question_prompt_lines` 只校验 list 类型不校验元素为 str，`[123]` 通过校验后下游 `'\n'.join` 抛 TypeError；错误消息名不副实；`section_pattern` 类型未校验，无效正则仅被 loader 静默 warning + 跳过 | 补元素 str 校验；schema 增加正则可编译性校验（启动即报错） |

### C. 线程与状态

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| C1 | `ui/default_app.py:728/736/746/1093-1096/1171-1178/1258` 等 8 处 | 工作线程直接读 Tk 变量（`output_dir.get()`/`generate_pdf.get()`/`pipeline.*`/`content_type.get()`），Tk 非线程安全，可能抛 `RuntimeError: main thread is not in main loop` 或读到旧值 | 线程启动前在主线程快照传参，线程内不再碰 Tk 变量 |
| C2 | `shared/sympy_tools/sandbox.py:90-96` | 打包后 inprocess 回退路径替换全局 `sys.stdout = io.StringIO()`，多线程并行计算互相吞输出 | 用模块级锁串行化或线程局部 stdout |
| C3 | `shared/session.py:121-128` | `_save` 固定 `.tmp` 文件名 + 无锁（见 A2），并发写交错损坏 | 加锁 + 每实例独立 tmp 名 |

### D. 性能

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| D1 ❌ | `shared/pdf_compiler.py:108-136` | 每次编译 `copytree` 全量复制便携版字体目录（数百 MB 级），无缓存/增量 | 缓存到固定目录 + 时间戳校验 |
| D2 ❌ | `shared/pdf_compiler.py:423-428` | `item not in (images_map or {})` 比较对象是 section 标题 vs 目录名，语义错位 → 几乎无条件复制 tex_dir 全部子目录（含 `__pycache__`） | 修正比较逻辑或只复制 images 目录 |
| D3 | `shared/shidianguji_playwright.py:19-32` | `is_playwright_available()` 每次 launch+close 一个 Chromium 来"检测"，`extract_chapter`/`_search_detail_url` 各调一次，一道文言文题前置搜索启动 2-3 次浏览器 | 模块级缓存检测结果 |
| D4 | `shared/sympy_tools/sandbox.py:35` | 每次计算 fork 新 Python 子进程 + 冷导入 sympy（约 1-3s/次），工具循环频繁调用时显著拖慢 | 常驻 worker 进程池或进程内 + 锁串行 |
| D5 | `core/docx_report.py:24, 507-525` | 模块导入即拉起 matplotlib 并扫全系统字体（`_find_cjk_font` 遍历 ttflist，首载 0.5-2s）；每条批注每个 `$...$` 公式单独 `plt.figure`+`savefig`（100-500ms/张） | formula_render 惰性导入；相同公式体缓存 PNG；复用单个 figure |
| D6 | `ui/widgets.py:5-13` | LogPanel 无限增长（长任务内存持续上升）；每行 `update_idletasks()` 强制冲刷拖慢主线程 | 超过 N 行（如 5000）裁剪头部；去掉 update_idletasks |
| D7 | `core/idml_extractor.py:409-419` | `_is_useless` 每段前向/反向线性扫描上下文 → 长文 O(n²) | 一次遍历缓存 prev/next |
| D8 | `shared/chinese_classics_tools.py:336-363` | `diff_characters` n-gram 全量扫描 + 反复 `given.find`，长文本 O(n²) | 加匹配位置缓存 |

### E. 安全加固（次要）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| E1 | `shared/sympy_tools/templates.py:467-468` | `method`/`order` 参数未经 `json_repr` 转义直接嵌入生成的执行代码（代码注入面，目前被 `check_dangerous` 兜底） | 参数统一过 `json_repr` |
| E2 | `shared/docx_format_enhancer.py:185-186` | 单个常见汉字（如"的"）不跳过增强逻辑，可能被 `inject_format_markers` 误包裹到文中任意位置 | 修正跳过条件 |
| E3 | `shared/web_tools.py:88, 99` | `requests.Session()` 未 close（连接池泄漏）；GET 未 `raise_for_status` | with 语句 + 状态码检查 |
| E4 | `core/idml_extractor.py:429-433` | 裸文件名时 `os.makedirs(dirname="")` → FileNotFoundError | dirname 为空时用 "." |

### F. 重复代码（可下沉/抽取）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| F1 | `shared/physics_tools.py` vs `shared/chemistry_tools.py` | 两个解题工具约 90% 逐行相同（仅类名/文案/落盘文件名不同），ADR-0023 只去重了凭证部分 | 抽公共基类 + 学科子类 |
| F2 | 7 个 `subject.py` | `get_question_prompt`/`get_review_prompt` 的拼接逻辑 3 份逐字相同 + 4 种变体（历史 react 评审无工具指令、英语工具指令只有名字列表）；历史/语文 `split_lecture` 也几乎逐字重复 | 下沉 `BaseSubjectApp` 模板方法 + 差异开关（如 `_append_tool_instructions`/`_post_split_hook`） |
| F3 | `shared/chemistry_tools.py:52`、`shared/sympy_tools/tools.py:400`、`shared/sympy_tools/templates.py:189` | 化学式解析三处重复（注释自认需"保持同步"，易漂移） | 收敛为单一实现 |
| F4 ❌ | `shared/latex_generator.py:59-75` vs `shared/review_latex.py:19-36` | `_LATEX_SPECIAL` + `_escape_text` 重复定义（review_latex 多 `#` 一项） | 收敛到一处 |
| F5 | `shared/split_post_utils.py:15-46` vs `:49-90` | `remove_navigation_units` 与 `mark_navigation_units` 遍历逻辑几乎相同 | 抽公共遍历函数 |
| F6 | `ui/default_app.py:628`、`:1130-1133`、`core/docx_report.py:216` | 自然排序三份拷贝 | 统一到 core 工具函数 |

### G. 打包与发布

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| G1 | `.gitignore:13`、`specs/` | `*.spec` 规则误伤 PyInstaller spec，唯一 spec 未入库；packaging.md 声称每学科一个 spec | `.gitignore` 加 `!specs/*.spec` 并入库 |
| G2 | `specs/高中物理.spec:25-74` | hiddenimports 缺 `core.base_subject`/`core.config_schema`/`core.docx_report`/`core.pipeline_service`/`core.unit_detect`/`shared.comment_marker`/`shared.formula_render`/`shared.plan_tools`/`shared.session`/`shared.shidianguji_playwright` 等动态导入模块 | 脚本自动收集生成 hiddenimports 或补全清单 |
| G3 | `subjects/*/main.py`、`docs/packaging.md:200-227` | 文档承诺「config.json 放 exe 同级、用户可编辑」，实际 subject_dir 全部指向 `_MEIPASS`（`_internal`）；小学数学 `_ensure_config` 复制源=目标（no-op），其余 6 科没有 `_ensure_config` | 按文档落地：打包后 subject_dir 返回 exe 目录 + 首次运行从内置复制 |
| G4 | `subjects/初中英语v3.0/app.py:5`、`高中化学v3.0/app.py:5`、`小学语文v3.0/app.py:5` | `sys.path[0].replace(r'subjects\\高中化学', '')` 是 Windows 反斜杠 hack，macOS/Linux 上为死代码；7 个 app.py 三种风格并存 | 统一为小学数学的 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 写法 |

### H. 文档同步（违反 AGENTS.md 约定）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| H1 | `AGENTS.md`「SubjectApp 接口」章节 | 整体过时：列了已删除的 `get_knowledge_prompt`（实际为 `get_review_prompt`）、旧签名 `proofread_one(api_url, api_key, model, ...)`（实际 `(ctx, q_dir, q_name, generate_pdf, source_mode, archive_root)`）、`split_exam` 缺 options、"api_client 接受 max_loops"（实际在 `SessionContext.max_loops`）。照文档新建学科必然接口不兼容 | 按 `core/base_subject.py` 实际接口更新 |
| H2 | `CONTEXT.md:4` | 状态浓缩句过时：ADR-0021/0023/0024/0025/0026/0027 写「待落地」，实际 ADR 文件状态字段均已「已实现」 | 同步状态句 |

### I. 工程配置

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| I1 | `.github/workflows/test.yml` | 无 pip/apt 依赖缓存；无 ruff lint 步骤（pre-commit 配了 ruff，CI 从不跑）；无 concurrency 组；matrix 仅 py3.12 × {ubuntu, windows} 无 macOS；装了 pytest-cov 从不以 --cov 运行 | 加缓存 + ruff 门禁 + concurrency + 可选 macOS/coverage |
| I2 | `core/config_loader.py:22-38` | 缓存键 `(subject_dir, config_mtime, env_mtime)` 缺 `agent_prompt.json` mtime → 热更新提示词不生效（依赖 `clear_config_cache()` 硬清）；缓存随 mtime 变化无限增长 | 缓存键加 agent_prompt mtime；或进程内单例 + 显式失效 |
| I3 | `scripts/_search_results/_prompt_preview_*.md` | `preview_react_prompt.py` 的生成产物被 git 追踪，违反 AGENTS.md 中间产物命名约束（`tests/_search_results` 的 5 个 fixture 是合理入库，两者不一致） | `git rm --cached` + .gitignore 补充 |

---

## 三、P3 级问题（分组清单）

### 1. lint 债（392 项）
- 分布：`tests/test_fix_latex_escapes.py`（52）、`core/defaults.py`（42）、`ui/default_app.py`（37）、`shared/latex_generator.py`（31）、`shared/chinese_classics_tools.py`（31）、`core/api_client.py`（20）等
- 规则：E501 168 / W605 59 / F541 35 / E702 32 / E741 23 / E402 19 / E701 16 / F841 13 / I001 10 / F401 8 等
- 建议：一次 lint 清理提交（`--fix` 修 115 个，`--unsafe-fixes` 覆盖更大），CI 加 ruff 门禁防回潮；pre-commit 版本（v0.11.0）与本地安装（0.16.0）不一致需统一

### 2. 死代码
- `core/pipeline_service.py` 全文件骨架（无生产引用，见 P2-A1）
- `shared/free_proofread.py`：`is_free_proofread_mode`、`get_free_proofread_output_dir` 零调用
- `shared/bash_tool.py:307-390`：`set_current_file`/`get_current_file`/`_next_mark_number`/`_sanitize_proofread_text`/`_validate_latex_braces`（ADR-0016 半接线产物，无生产调用方）
- `core/base_subject.generate_knowledge`（ADR-0017 已废弃）
- `core/docx_report.py:147-150`：`if gid in used_ids` 永不成立（gid 单调递增）
- ~~`shared/latex_generator.py:341-343`：`if not available_files: pass`~~（LaTeX 下线）；`templates.py:465`：`domain` 死参数
- `ui/default_app.py:98-103`：`show_intent_clean_option`/`show_source_modes`/`show_exec_modes` 定义后无人消费；`:865-866` `img_dir`/`fname` 死变量；`intent_clean_enabled` 无 UI 控件恒真

### 3. 测试工程
- `pytest.ini` 与 `pyproject.toml` 双源配置：实测 pytest 输出 `WARNING: ignoring pytest config in pyproject.toml!` → 删 pytest.ini 只留 pyproject
- 34 个测试文件用 `unittest.TestCase` 与 pytest 风格函数混用
- `temp_dir` 类 fixture 在 4 个测试文件重复定义，未复用 `conftest.py:9`
- `scripts/test_e2e_agent_pipeline.py` 是测试却放 scripts/（无标记，CI 永不运行）
- `shared/bash_tool.EditFileTool` 仅测试引用（接线前需先修 P1-3）

### 4. 依赖
- `lxml>=5.0`（requirements.txt + spec hiddenimports）主树 0 引用（idml 用 `xml.etree`）→ 移除或注明用途
- `.ruff_cache/` 未入根 .gitignore（靠 ruff 自生成嵌套 .gitignore，机制脆弱）

### 5. 风格与细节
- 7 个 `subject.py` 尾部 3-5 个多余空行；`agent_prompt_*_backup*.json` 4 份历史备份被追踪（建议 `git rm --cached`）
- `subjects/高中物理v3.0/config.json:20-21`：两处 "6." 编号重复（应为 6、7）
- `subjects/小学数学v3.0/config.json:103`：`"\\d+.*"` 过宽（`^\*\*\d+.*\*\*.*$` 会误切「\*\*2026年\*\*」等数字开头行），建议收紧为 `\d+[.、)]`
- `core/api_client._post_chat` 重复 `resp.json()`；`defaults.normalize_option_spacing` 函数内重复 `import re`；`unit_detect.scan_question_dirs` str→Path 冗余往返
- `ui/widgets.ApiDialog._do_save`：输入不完整静默 return 无提示
- `core/env_config.save_env_config`：追加键写 UPPER 而保留键维持原大小写；不剥引号/行内注释（`API_KEY=sk # note` 注释会进值）
- `core/manual_split.py:104-155` 与 `parse_unit_markers` 委托式整体重复，可合并参数化
- `core/docx_report._convert_multiline_tables:291`：`re.split(r" {2,}")` 会把含双空格的单元格内容错误切分
- `core/logging_utils.py:115-125`：新旧双轨日志（`_log_func` + logging），`_initialized` 读取无锁；`emit` 吞 UI 回调异常无降级日志
- `shared/chinese_classics_tools.py:890`：`except (json.JSONDecodeError, Exception)` 冗余（前者是后者子类）；`:859` `startswith("[E")` 与任何返回格式不匹配
- ~~`shared/review_latex.py:58`：所有换行（含空行）一律转 `\\`，空行产生 LaTeX "no line here to end" 警告~~（LaTeX 下线）
- `shared/sympy_tools/safety.py:12-16`：黑名单 `\bhttp\b`/`\bsubprocess\b` 误伤注释/字符串字面量
- `shared/image_utils.py:88-94`：不同源目录同名图片静默先到先得
- `shared/plan_tools.py:71`：`_run` 返回 dict 与 BaseTool 常规 str 返回不一致
- `shared/physics_tools.py:13`：`import threading` 未使用；`split_post_utils.py:21,64`、`sympy_tools/tools.py:395` 函数内重复 import/编译正则
- `ui/default_app.py:397`：悬挂 docstring（非函数首行的字符串语句）

---

## 四、修复路线建议（四批）

1. **第一批（安全 + 卡死，改动小收益大）**：P1-1（按钮 finally + task_running）、P1-2/P1-3（BashTool/EditFileTool 加固）、P1-4（子进程 kill）、P1-5（换行正则）
2. **第二批（数据正确性）**：B1（跨行标记正则单一源，连同 F 组正则拷贝收敛）、B2（docx 锚点 XML 转义）、B3（目录识别统一到 unit_detect）、C1（Tk 变量快照）
3. **第三批（发布阻断）**：P1-6/P1-7（spec + lock 同步 + CI 校验）、G 组（specs 入库、hiddenimports、subject_dir 落地）
4. **第四批（架构收尾 + 工程卫生）**：A 组（pipeline_service 搬迁、session 恢复、管线校验）、D 组性能、F1/F2 去重、lint 清零 + CI 门禁、H 组文档同步、P3 死代码清理

---

## 附录 A：ruff 问题分布（Top 12 文件）

| 文件 | 问题数 |
|---|---|
| tests/test_fix_latex_escapes.py | 52 |
| core/defaults.py | 42 |
| ui/default_app.py | 37 |
| shared/latex_generator.py | 31 |
| shared/chinese_classics_tools.py | 31 |
| core/api_client.py | 20 |
| shared/sympy_tools/tools.py | 13 |
| core/docx_report.py | 11 |
| tests/test_math_pdf.py | 8 |
| tools/build_minimal_texlive.py | 7 |
| shared/chemistry_tools.py | 7 |
| tests/test_split_modes.py | 6 |

## 附录 B：已复现验证记录

| 问题 | 复现方式 | 结果 |
|---|---|---|
| P1-2 BashTool 绕过 | `_validate_bash_command('python -c "import shutil; shutil.rmtree(...)"', '/allowed/dir')` | 返回 None（放行）；`cat /etc/passwd`、`rm -rf` 正确拦截 |
| P1-4 子进程泄漏 | `subprocess.run(['sleep','5'], timeout=1)` | TimeoutExpired 抛出后 sleep 进程继续存活 |
| P1-5 LaTeX 损坏 | `'\\noindent'.replace('\\n','\n')` | `\noindent` → 换行 + `oindent` |
| B3 目录识别漂移 | 13 个目录名逐一对比 UI 规则与 `is_unit_dir` | 「错题集」「试题分类」「题目汇总」「单元A」「板块A」5 类判定分歧 |
| 双源 pytest 配置 | 运行测试 | 输出 `WARNING: ignoring pytest config in pyproject.toml!` |

## 附录 C：正面确认（非问题）

- 7 科 SubjectApp 接口一致性有测试护栏且全绿，无 P0 接口漂移；`core/` 零学科特定逻辑
- `.gitignore` 已正确覆盖 `build/`、`dist/`、`output/`、`.DS_Store`、`__pycache__`、`.env`、`*.log`
- 7 科 config.json 均通过 `validate_config`；除 lxml 外所有依赖均有真实引用
- `test_pipeline_service.py` 诚实地标注骨架契约而非假绿（符合 AGENTS.md 测试原则）
- `SessionManager._save` 采用原子写入（tmp + `os.replace`）；物理/化学凭证已用 `threading.local()` 隔离（ADR-0023 落地）
