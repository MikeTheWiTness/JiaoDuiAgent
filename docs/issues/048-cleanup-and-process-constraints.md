# Issue 048：清理与流程约束（不立 ADR，仅执行清单 + AGENTS.md 补充）

**类型**：清理 + 流程约定
**关联 ADR**：本 Issue 不是决策记录；与 ADR-0021~0027 的支线落地无关，是一组可独立执行的项

---

## 背景

2026-07-23 架构审查发现的「低风险清理 + 不可逆性弱」事项——既达不到「难以逆转」也不构成"真正的权衡决策"（ADR 三准则——难以逆转 / 令人惊讶 / 真正抉择——三者缺一），不立 ADR。但它们让仓库变脏与状态失配，需要批量执行。

另一组是流程约束：仓库当前文档（ADR 状态字段、docs/issues）和代码版本控制脱节——ADR 落地后状态字段不更新，docs/issues 与对应 commit 不在同一次提交里。需要写进 AGENTS.md 成为工作约定。

---

## 清理清单（H）

### H1 删除根目录测试中间产物
- 删 `_smart_split_raw_attempt1.md`、`_smart_split_raw_attempt2.md`（违反 AGENTS.md 中间产物保存路径 `_smart_split_raw.md` 命名约定）
- `.gitignore` 加 `_smart_split_raw*.md`（允许规范命名的 `_smart_split_raw.md`，禁乱命 attempt 后缀的文件被追踪）

### H2 补全 `.gitignore`
现有 `.gitignore` 已覆盖 `dist/ build/ output/ *.egg-info __pycache__ .env*`。补漏：
- `.DS_Store`（根/docs/subjects 都已生成多个，untracked）
- `/.kilo/`（kilo worktree 目录，防被 `git add .` 误入）
- `.pytest_cache/`（已存在但未显式忽略）
- `.zcode/`（ZCode 本地会话目录）
- `tests/_search_results/`（测试中间产物）

### H3 一次性脚本归位
- `create_issues.py`（432 行，硬编码 issue 编号的一次性脚本）迁到 `tools/` 或 `scripts/`
- README 第 17 行项目结构树补 `tools/` 子说明

### H4 多份 AI 约定文件合并
根目录同时存在 `AGENTS.md` / `CLAUDE.md` / `Trae.md`。建议保留 `AGENTS.md`（ZCode 等工具识别）+ README，`CLAUDE.md` / `Trae.md` 内容合并入 AGENTS.md 或迁 `docs/`，单点维护。

### H5 `docs/` 杂项归类
- `docs/_all_prompts_full.md` / `docs/prompt_summary.md` 与 adr/issues 混级，迁到 `docs/notes/` 或 `docs/prompts/`
- `docs/prd/` 命名风格不统一（`react-mechanism.md` 无编号 vs `0009-knowledge-dimension-overlay.md` 有编号），统一为带编号

### H6 `memory/MEMORY.md` 沉淀
现仅 1 行，与 17 个 ADR 实际演进体量严重失衡。把它沉淀为「跨会话决策索引 + 已落地 ADR 列表」，至少列全部 ADR 的运行态（落地/待办/被取代）。

### H7 ADR / Issue 立即 `git add`
`git status` 显示 ADR-0019/0020 + Issue 039-047 仍 untracked，但对应代码已合并。立即 `git add docs/adr docs/issues` 并提交——与 I1 约定一致，本批则是事后补救。

### H8 README 学科表与项目结构树同步
- README "已完成学科"表 6 行，`subjects/` 实际 7 个（漏高中历史），补一行或注明未正式交付
- README 项目结构树未列实际存在的 `core/base_subject.py` / `config_schema.py` / `idml_extractor.py` / `session_context.py` 等，同步结构树或改为概述

---

## 流程约束（I）

### I1 ADR 落地后状态字段必须同步更新
写入 AGENTS.md「常用工作流」一节补约束：

> **ADR 状态字段同步约定**：ADR 对应实现 commit 合并后，立即把 ADR 顶部「状态」字段从「已接受」「设计中」「待落地」等改为「已实现」，并附 commit 号（格式参照 ADR-0008 的 `已实现（commit b878670）`）。CONTEXT.md 的状态浓缩句同步更新。

ADR-0008 已示范此写法。本约定是在 ADR-0016/0017/0018 状态滞后（声称"待落地"但已合并）事故后总结。

### I2 Issue 文档与对应 commit 必须同 PR 提交
写入 AGENTS.md 补约束：

> **Issue / ADR 与代码同提交**：`docs/issues/NNN-*.md` 与对应 feat commit 必须在同一 PR 提交，不能 untracked 滞留。Issue 文档先于或同于实现提交，便于审查时回溯决策依据。事后补救要专设一次「文档同步」提交。

### I3 AGENTS.md 中间产物约定已存在，但需补一条命名约束
AGENTS.md「中间产物保留」一节已列 `_smart_split_raw.md` / `_校对报告.md` / `_校对数据.json` 三种关键产物路径。补一句：

> 中间产物文件命名必须遵循约定路径名（如 `_smart_split_raw.md`），禁用自由命名的 attempt / 副本文件（如 `_smart_split_raw_attempt1.md`）被 git 追踪；多轮中间产物可改为文件内分节，而非分散多文件。

---

## 明确不做

- **`requirements.txt` 退役**：与 ADR-0027 C1 范围交叉，不在本 Issue 接手。
- **CI 配置修正**：与 ADR-0027 C2-C5 范围交叉（去 `|| true`、双平台、删死规则），不在本 Issue 接手。
- **ADR-0019 ~ ADR-0027 各自落地实施**：见各自 ADR；本 Issue 只做与 ADR 交叉之外的清理与流程约定写入。

## 执行优先级

H7、I1、I2 优先（文档失配积压，影响后续 grill 与 review 判断）；H8 次之（不修正就持续误导审查）。H1-H6 与 I3 可随手做提交。