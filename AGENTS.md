# AGENTS.md

本文件记录对 AI 编码助手的持久化要求与工作约定。仓库唯一 AI 约定文件（原 CLAUDE.md / Trae.md 已合并入本文，不再单独维护）。

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

## 测试原则

- 禁止为了通过测试而削弱测试效果
- 测试必须能代表真实情况，不能削减需求来让测试通过

## 中间产物保留

- 所有 LLM 返回的原始内容（含 reasoning/thinking）、工具调用请求与返回内容、解析中间结果，**必须写入文件保留**，不得仅在日志中输出。用于后期排查问题时回溯完整调用链。
- 关键中间产物的保存路径：
  - 智能分割原始输出 → `_smart_split_raw.md`（`shared/smart_split.py:_dump_smart_split_raw`）
  - 校对 LLM 原始返回 + 工具调用日志 → `_校对报告.md`（`core/defaults.py:default_proofread_one`）；LLM 思考内容（reasoning_content）逐轮写入 `_API对话记录.md`（`core/api_client.py:_save_conversation_log`），不得写入校对报告
  - 校对结构化解析结果 → `_校对数据.json`（`core/parsing.py:save_proofread_json`）
  - API 调用日志 → 通过 `core/logging_utils.py` 的 `log()` 函数输出到日志面板
- **命名约束**：中间产物文件命名必须遵循约定路径名（如 `_smart_split_raw.md`），禁用自由命名的 attempt / 副本文件（如 `_smart_split_raw_attempt1.md`）被 git 追踪；多轮中间产物可改为文件内分节，而非分散多文件。

## 错误日志

- 所有异常必须记录完整的上下文信息（触发异常的函数名、输入参数摘要、完整 traceback），不得只记录异常消息
- 使用 `log()` 函数（`core/logging_utils.py`）输出到 UI 日志面板，同时落盘到日志文件
- 生产环境错误日志必须包含：时间戳、模块名、错误级别、完整堆栈
- API 调用失败时必须记录：请求 URL、模型名、HTTP 状态码、响应体摘要

---

## 常用工作流

| 技能 | 时机 | 产出 |
|---|---|---|
| `/grill-with-docs` | 设计讨论阶段 | 更新 CONTEXT.md，完成后输出一个 ADR |
| `/to-prd` | grill 结束后，若内容变动大 | 生成 PRD 文档到 issue tracker |
| `/to-issues` | PRD 完成后 | 拆分为可独立领取的 issue |
| `/implement` | 开始编码 | 按 issues 执行实现：预重构 → 构建 → 测试 → review → 提交。 |
| `/tdd` | 测试驱动开发 | 红→绿→重构循环，测试必须代表真实需求 |

## `/grill-with-docs` 时的行为准则

- 只记录，不执行。Grill 阶段收集问题、记录发现，标记为待处理，不要马上改代码
- 等所有问题问完、ADRs 输出后再进入执行阶段
- 发现的 bug/疏忽记录下来，在 `/to-issues` 阶段生成修复任务

---

## 流程约束

### ADR 状态字段同步约定

ADR 对应实现 commit 合并后，**立即**把 ADR 顶部「状态」字段从「已接受」「设计中」「待落地」等改为「已实现」，并附 commit 号（格式参照 ADR-0008 的 `已实现（commit b878670）`）。CONTEXT.md 的状态浓缩句同步更新。

### Issue 文档与对应 commit 同 PR 提交

`docs/issues/NNN-*.md` 与对应 feat commit 必须在**同一 PR** 提交，不能 untracked 滞留。Issue 文档先于或同于实现提交，便于审查时回溯决策依据。事后补救要专设一次「文档同步」提交。

---

## 架构设计约束（不可违反）

1. **`core/` 零学科特定逻辑**。无 `if subject == "语文"` 分支，无硬编码工具映射。`api_client.py` 接受 `max_loops` 参数，不从学科名推算。
2. **`subject.py` 拥有全部业务逻辑**。工具、提示词、工具调用限制、拆分逻辑、校对流程、钩子——全部在学科的 `subject.py` 定义。可复用 `core/defaults`，也可完全替换。
3. **`app.py` 拥有 UI**。每个学科有自己的 GUI。`ui/default_app.py` 是参考模板（可继承），非共享单体。`ui/widgets.py` 提供可复用构建块。
4. **学科目录自治**。新增学科 = 新建目录含 `main.py` + `subject.py` + `app.py` + `config.json`。`core/`、`shared/`、`ui/` 零改动。
5. **学科目录使用中文名**（如 `高中物理v3.0/`）。`main.py` 通过 `importlib.util.spec_from_file_location` 按文件路径加载，非模块名导入。`core/`、`shared/`、`ui/` 使用英文名和正常 import。
6. **每个学科独立 `.env`**。`core.env_config` 接受 `subject_dir` 参数。
7. **`core/defaults.py` 是参考实现，非强制**。修改 defaults 不影响已自定义实现的学科。

---

## SubjectApp 接口

每个 `subject.py` 必须定义 `SubjectApp` 类，含以下方法：

```python
class SubjectApp:
    name: str                          # 显示名（如 "高中物理"）

    def __init__(self, subject_dir):   # subject_dir = 本学科目录路径
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self) -> list:     # 工具实例列表
    def get_max_tool_loops(self) -> int
    def get_tool_instructions(self) -> str
    def get_question_prompt(self) -> str
    def get_knowledge_prompt(self) -> str

    # 拆分
    def split_lecture(self, md_file, output_root, base_name, options)
    def split_exam(self, md_file, output_root, base_name)
    def generate_knowledge(self, md_file, output_root, base_name)

    # 校对
    def proofread_one(self, api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf)
    def collect_paper_dirs(self, base_path) -> list

    # 钩子（默认 no-op）
    def pre_proofread_hook(self, md_text) -> str
    def post_proofread_hook(self, result, q_dir): return result
```

---

## 编码约定

- **命名**：变量和函数名用英文；注释可用中文。
- **导入**：`shared/sympy_tools/` 内使用相对导入（如 `from .safety import`）。
- **线程安全**：`core.logging_utils.log()` 使用 `_log_lock`。GUI 更新必须用 `root.after()`。
- **Windows 子进程**：使用 `CREATE_NO_WINDOW` 标志避免黑窗口。
- **新代码不加注释**，除非显式要求。

---

## 相关文档

- [打包指南](docs/packaging.md)
- [架构决策记录](docs/adr/)
- [架构速查](memory/MEMORY.md)
