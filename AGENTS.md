# AGENTS.md

本文件是仓库唯一的 AI 约定文件，记录对 AI 编码助手的持久化要求与工作约定。

---

## 项目概述

K-12 多学科 AI 校对工具集 —— **每个学科是独立程序**，拥有自己的业务逻辑和 UI。共享层（`core/`、`shared/`、`ui/`）只提供纯工具和默认模板，学科可自由复用或完全重写。

**核心设计原则**：学科拥有业务逻辑和 UI，共享层零学科特定代码。

---

## 工作语言

全程使用简体中文交流。

## 环境要求

- `pip install` 优先使用清华源：
  ```bash
  pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <package>
  ```
- 开发环境为 macOS；exe 打包在 Windows 上完成（打包阶段迁移到 Windows 执行）

## 测试原则

以「用测试锁定行为契约」为目的；「红→绿→重构」只适用于行为可规格化、有稳定接缝、长期存活的代码，其余按层决策：

- 禁止为了通过测试而削弱测试效果；糟糕的测试（实现耦合、同义反复断言、脆弱）比不写更糟，会制造虚假安全感
- 测试必须能代表真实情况，预期值必须来自独立来源（已知样本 / 规格），不得用与实现相同的逻辑重算（同义反复）
- **按层决策**：
  - `core/`、`shared/` 的确定性逻辑（拆分、解析、工具、配置）：红→绿→重构，先定接缝（seam），接缝越少越好
  - LLM 编排链路：**不硬套红→绿**——mock 模型测编排逻辑，配合契约/格式校验 + golden 样本（代表真实情况）
  - 纯 GUI 展示层：少测/不测，只测业务逻辑不测像素
  - 探索期新功能：先 spike，契约稳定后再固化测试
- 遗留代码重构：先加接缝/预重构 + 刻画测试（锁定现状行为）→ 再重构 → 新功能才 TDD；接缝不存在时 TDD 无法启动

## 中间产物保留

- 所有 LLM 返回的原始内容（含 reasoning/thinking）、工具调用请求与返回内容、解析中间结果，**必须写入文件保留**，不得仅在日志中输出。用于后期排查问题时回溯完整调用链。
- 关键中间产物的保存路径：
  - 智能分割原始输出 → `_smart_split_raw.md`（`shared/smart_split.py:_dump_smart_split_raw`）
  - 校对 LLM 原始返回 + 工具调用日志 → `_校对报告.md`（`core/defaults.py:default_proofread_one`）；LLM 思考内容（reasoning_content）逐轮写入 `_API对话记录.md`（`core/api_client.py:_save_conversation_log`），不得写入校对报告
  - 校对结构化解析结果 → `_校对数据.json`（`core/parsing.py:save_proofread_json`）
  - 校对断点续传快照 → `_校对续传.json`（`core/api_client.py`，轮次边界原子写；正常完成删除、中断/出错保留；命名约束：禁用自由命名副本文件，损坏重命名 `_校对续传.corrupt.json` 见 ADR-0029）
  - API 调用日志 → 通过 `core/logging_utils.py` 的 `log()` 函数输出到日志面板
- **命名约束**：中间产物文件命名必须遵循约定路径名（如 `_smart_split_raw.md`），禁用自由命名的 attempt / 副本文件（如 `_smart_split_raw_attempt1.md`）被 git 追踪；多轮中间产物可改为文件内分节，而非分散多文件。

## 错误日志

- 所有异常必须记录完整的上下文信息（触发异常的函数名、输入参数摘要、完整 traceback），不得只记录异常消息
- 使用 `log()` 函数（`core/logging_utils.py`）输出到 UI 日志面板，同时落盘到日志文件
- 生产环境错误日志必须包含：时间戳、模块名、错误级别、完整堆栈
- API 调用失败时必须记录：请求 URL、模型名、HTTP 状态码、响应体摘要

---

## 常用工作流

| 阶段 | 机制 / 约定 | 产出 |
|---|---|---|
| 设计讨论 | grill 访谈（见「grill 访谈」） | 更新 `CONTEXT.md`；输出 ADR 到 `docs/adr/` |
| 计划 | DSH 计划模式（`/plan` + `exit_plan_mode`） | 复杂需求 → ADR（背景 + 决策）；简单需求直接拆 issue |
| 拆分 issue | 垂直切片 + 阻塞边（见「issue 拆分约定」） | `docs/issues/NNN-*.md`，可独立领取 |
| 实现 | 预重构 → 构建 → 测试 → review → 提交（红→绿→重构，见「测试原则」） | feat commit + issue 文档同 PR |
| 进度跟踪 | DSH `todo_write`（当前步骤）+ `goal`（跨轮长期目标） | 会话内任务清单 / 持久化目标 |

## grill 访谈（设计讨论）

对计划或设计做逐题质询，一次只问一个问题，等答复后再问下一个；一次多问会让用户应接不暇。

- 只记录，不执行：收集问题、记录发现，标记待处理，不马上改代码
- 事实可查的（文件、代码、环境）先查，不要问；决策才问用户，每题给出推荐答案
- 沿决策树逐分支推进，先解决依赖关系；等所有问题问完、ADR 输出后再进入执行
- 同步维护领域模型：术语定稿即更新 `CONTEXT.md`（只收术语，不收实现细节）；值得记的取舍写成 ADR 到 `docs/adr/`，仅在「难逆转 + 无背景难懂 + 真有取舍」三者齐备时才立 ADR
- 发现的 bug/疏忽记录下来，在「拆分 issue」阶段生成修复任务（见「issue 拆分约定」）

---

## 流程约束

### issue 拆分约定

拆成 `docs/issues/NNN-*.md`（**三位数**，从 001 起按依赖顺序——阻塞者在前，禁止两位数）：

- **垂直切片（tracer bullet）**：每个 issue 切一条贯穿 schema/API/UI/tests 全层的窄路径，完成即可独立演示/验证、单窗口塞得下。**禁止水平切片**（一层全做完再做下一层）
- **阻塞边**：每个 issue 用「Blocked by」声明依赖的 issue；无依赖的立即开工，按 frontier（依赖全完成）推进
- **先预重构**：让改动变容易的预重构放最前
- **宽重构走 expand–contract**：机械式全局改动（改列名/改共享符号）不硬切竖片——先并存新形式（expand）→ 按包/目录分批迁移（每批一个 issue，被 expand 阻塞，逐批 green）→ 最后删旧形式（contract，被所有迁移批阻塞）
- 每个 issue 含 **acceptance criteria** 勾选清单
- **不写具体文件路径和代码片段**（会快速过时）；例外——prototype 产出的状态机/reducer/schema/type shape 可内联并注明来源

### ADR 状态字段同步约定

ADR 对应实现 commit 合并后，**立即**把 ADR 顶部「状态」字段从「已接受」「设计中」「待落地」等改为「已实现」，并附 commit 号（格式参照 ADR-0008 的 `已实现（commit b878670）`）。CONTEXT.md 的状态浓缩句同步更新。

### Issue 文档与对应 commit 同 PR 提交

`docs/issues/NNN-*.md` 与对应 feat commit 必须在**同一 PR** 提交，不能 untracked 滞留。Issue 文档先于或同于实现提交，便于审查时回溯决策依据。事后补救要专设一次「文档同步」提交。

---

## 架构设计约束（不可违反）

1. **`core/` 零学科特定逻辑**。无 `if subject == "语文"` 分支，无硬编码工具映射。`max_loops` 由 `SessionContext` 携带（`api_client.call_api(ctx, ...)` 读取 `ctx.max_loops`），不从学科名推算。
2. **`subject.py` 拥有全部业务逻辑**。工具、提示词、工具调用限制、拆分逻辑、校对流程、钩子——全部在学科的 `subject.py` 定义。可复用 `core/defaults`，也可完全替换。
3. **`app.py` 拥有 UI**。每个学科有自己的 GUI。`ui/default_app.py` 是参考模板（可继承），非共享单体。`ui/widgets.py` 提供可复用构建块。
4. **学科目录自治**。新增学科 = 新建目录含 `main.py` + `subject.py` + `app.py` + `config.json`。`core/`、`shared/`、`ui/` 零改动。
5. **学科目录使用中文名**（如 `高中物理v3.0/`）。`main.py` 通过 `importlib.util.spec_from_file_location` 按文件路径加载，非模块名导入。`core/`、`shared/`、`ui/` 使用英文名和正常 import。
6. **每个学科独立 `.env`**。`core.env_config` 接受 `subject_dir` 参数。
7. **`core/defaults.py` 是参考实现，非强制**。修改 defaults 不影响已自定义实现的学科。

---

## SubjectApp 接口

每个 `subject.py` 定义 `SubjectApp` 类，继承 `core.base_subject.BaseSubjectApp`。零差异方法（`split_exam`、`collect_paper_dirs`、`get_ui_features`、`get_supported_file_types`、`proofread_one` 等）由基类提供，学科只覆盖学科化方法：

```python
class SubjectApp(BaseSubjectApp):
    # 类属性
    name: str          # 显示名（如 "高中物理"）
    LEVEL: str         # 学段
    SUBJECT: str       # 学科

    def __init__(self, subject_dir):   # subject_dir = 本学科目录路径
        super().__init__(subject_dir)  # 基类：load_config + build_tools

    # 学科化方法（必须覆盖）
    def build_tools(self) -> list           # 工具实例列表
    def get_max_tool_loops(self) -> int
    def get_tool_instructions(self) -> str
    def get_question_prompt(self) -> str
    def get_review_prompt(self) -> str      # 批注评审提示词

    # 拆分（讲义走此方法；试卷拆分由基类 split_exam 统一实现）
    def split_lecture(self, md_file, output_root, base_name, options)

    # 钩子（默认 no-op；高中语文覆盖 _build_pre_hook 注入文言文搜索）
    def pre_proofread_hook(self, md_text, api_url=None, api_key=None, model=None, q_dir=None) -> str
    def post_proofread_hook(self, result, q_dir): return result
```

`proofread_one(self, ctx, q_dir, q_name, generate_pdf, source_mode="试卷", archive_root=None, enable_format_fix=None)`、`split_exam(self, md_file, output_root, base_name, options=None)` 等零差异方法由 `BaseSubjectApp` 提供，学科无需重复实现。`generate_knowledge` 已废弃（ADR-0017）。

---

## 编码约定

- **命名**：变量和函数名用英文。
- **注释**：默认不加注释；确需注释时用中文。
- **导入**：`shared/sympy_tools/` 内使用相对导入（如 `from .safety import`）。
- **线程安全**：`core.logging_utils.log()` 使用 `_log_lock`。GUI 更新必须用 `root.after()`。
- **Windows 子进程**：使用 `CREATE_NO_WINDOW` 标志避免黑窗口。

---

## 相关文档

- [打包指南](docs/packaging.md)
- [架构决策记录](docs/adr/)
- [Issue 列表](docs/issues/)
- [架构速查](memory/MEMORY.md)
