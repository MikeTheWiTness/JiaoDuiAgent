# 校对工具（学科独立版）

K-12 多学科 AI 校对工具集 —— 每个学科独立程序，深度定制业务逻辑和界面

## 架构理念

**每个学科是一个自治单元**，拥有独立的业务逻辑、UI 界面和配置。共享层（`core/`、`shared/`、`ui/`）只提供纯工具和默认模板，学科可自由复用或完全重写。

为什么这样设计？
- 各学科的拆分逻辑差异很大（有的按模块拆、有的按题目拆）
- 各学科的校对内容差异很大（如语文需要原文联网校验，其他学科不需要）
- 各学科的 UI 需求可能不同（有的需要额外开关、有的需要全新面板）
- 大部分学科尚未正式施工，架构必须预留最大灵活性

## 项目结构

```
校对agent/
├── core/                     # 纯工具层（零业务逻辑、零 UI）
│   ├── paths.py              # 路径工具（兼容打包后）
│   ├── parsing.py            # LLM 输出解析
│   ├── api_client.py         # API 调用（HTTP、重试、工具循环）
│   ├── pandoc_utils.py       # Pandoc 转换
│   ├── env_config.py         # .env 读写
│   ├── logging_utils.py      # 日志
│   ├── config_loader.py      # config.json 加载器
│   └── defaults.py           # 默认拆分+校对参考实现
├── shared/                   # 共享工具库
│   ├── sympy_tools/          # 符号计算工具集
│   ├── web_tools.py          # 联网检索
│   ├── latex_generator.py    # Markdown → LaTeX
│   ├── pdf_compiler.py       # XeLaTeX 编译
│   ├── manual_split.py       # 人工标记分割
│   ├── smart_split.py        # 智能分割（LLM + XML标记）
│   ├── docx_comments.py      # Word 批注提取
│   ├── chinese_classics_tools.py  # 文言文/诗歌校对工具
│   ├── free_proofread.py     # 自由校对模式
│   ├── review_mode.py        # 批注评审模式
│   ├── review_latex.py       # 批注评审 PDF 生成
│   └── templates/
│       └── proofread_template.tex
├── ui/                       # UI 组件库 + 默认模板
│   ├── widgets.py            # 可复用组件（LogPanel/ApiDialog/ModeSelector）
│   └── default_app.py        # DefaultApp 默认界面模板
├── 高中物理/                  # 学科独立程序示例
│   ├── main.py               # 入口
│   ├── subject.py            # 业务逻辑（SubjectApp 类）
│   ├── app.py                # GUI（SubjectGui 类，继承 DefaultApp）
│   ├── config.json           # 配置（提示词 + 拆分规则）
│   ├── README.md
│   └── .env                  # API 配置（运行时生成）
├── specs/                    # 各学科的 PyInstaller spec 文件
│   └── 高中物理.spec
├── tools/                    # 构建工具
│   └── build_minimal_texlive.py
├── docs/
│   └── packaging.md          # 打包指南
├── requirements.txt
└── Trae.md                   # 项目系统提示词（给 AI 助手看的）
```

## 快速开始

### 环境要求

- Windows 10+
- Python 3.12
- Pandoc（Word 转 Markdown 用）
- TeX Live（可选，生成 PDF 用）

### 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 运行高中物理

```bash
python 高中物理/main.py
```

### 运行其他学科

```bash
python 高中语文/main.py
python 高中数学/main.py
# ...
```

每个学科独立运行，互不影响。

## 三层分离架构

每个学科目录包含 3 个核心文件，职责清晰分离：

| 文件 | 职责 | 可否自定义 |
|------|------|-----------|
| `subject.py` | 业务逻辑（工具、提示词、拆分、校对、钩子） | ✅ 完全自定义或复用 `core/defaults` |
| `app.py` | GUI 界面 | ✅ 完全自定义或继承 `ui/default_app.DefaultApp` |
| `main.py` | 入口（组装 subject + app） | 基本不需要改 |

### 扩展方式

**添加一个新学科**（以高中语文为例）：
1. 新建 `高中语文/` 目录
2. 创建 `config.json`（提示词 + 拆分规则）
3. 创建 `subject.py`：实现 `SubjectApp` 类
   - 工具集 → 覆盖 `build_tools()`
   - 调用次数 → 覆盖 `get_max_tool_loops()`
   - 工具指令 → 覆盖 `get_tool_instructions()`
   - 拆分逻辑 → 覆盖 `split_lecture()` / `split_exam()`
   - 校对钩子 → 覆盖 `pre/post_proofread_hook()`
   - 完全自定义校对 → 覆盖 `proofread_one()`
4. 创建 `app.py`：实现 `SubjectGui` 类
   - 简单定制：继承 `DefaultApp`，覆盖 `setup_extra_options()` 等扩展点
   - 深度定制：完全重写，自由组合 `ui/widgets.py` 中的组件
5. 创建 `main.py`：入口（复制高中物理的，基本不需要改）
6. 创建 `specs/高中语文.spec`：打包配置
7. `core/`、`shared/`、`ui/` **零改动**

## 已完成学科

| 学科 | 状态 | 工具数 | 拆分模式 | UI | 特色功能 |
|------|------|--------|---------|-----|---------|
| 高中物理 v1.8 | ✅ 完成 | 7 个（6个sympy + web_search） | title | 继承默认模板 | 符号计算、公式校验 |
| 高中语文 v2.0 | ✅ 完成 | 2 个（shidianguji + souyun + web_search） | 4 种（不拆分/规则/智能/人工标记） | 增强版默认模板 | 文言文/诗歌校验、自由校对、批注评审 |
| 更多学科... | 待施工 | — | — | — | — |

## 核心功能

### 四种来源模式

| 模式 | 说明 |
|------|------|
| 讲义模式 | 处理 Word 讲义文档，支持清理表格、提取知识文件夹 |
| 试卷模式 | 处理 Word 试卷文档，按题号拆分校对 |
| 自由校对模式 | 直接粘贴文本或上传图片/文件，无需 Word 格式 |
| 批注评审模式 | 提取 Word 文档中的批注，逐条评审批注质量并补充遗漏错误 |

### 五种执行模式

| 模式 | 说明 |
|------|------|
| 完整流程 | 转换 → 拆分 → 校对 → 生成报告，一键完成 |
| 仅转换 | 只将 Word 转换为 Markdown |
| 仅拆分 | 转换后按题目/板块拆分为多个单元 |
| 仅校对 | 对已拆分的题目目录进行 LLM 校对 |
| 仅生成PDF | 对已有校对结果生成 LaTeX PDF 报告 |

### 四种分割方式

| 方式 | 说明 |
|------|------|
| 不拆分 | 整份文档作为一个单元校对 |
| 普通规则 | 按标题/题号自动拆分 |
| 智能分割 | 调用 LLM 自动识别题目边界（XML 标记） |
| 人工标记 | 按 ###### 题目开始/结束 ###### 标记拆分 |

## 高中语文 v2.0 特色

作为目前功能最完整的学科，高中语文 v2.0 包含以下特色：

### 文言文 & 诗歌校对
- 自动识别文本类型（文言文 / 诗歌 / 现代文）
- 自动检索权威来源（诗词名句网、搜韵网）
- 逐字对比，标注异文和易错字

### 自由校对模式
- 直接粘贴文本、上传图片或 md 文件
- 不需要 Word 格式，适合零散内容快速校对
- 支持四种分割方式选择

### 批注评审模式
- 提取 Word 文档中的批注内容
- 逐条评审批注质量（正确/错误/需补充）
- 自动补充遗漏的错误点
- 生成逐条展开式 PDF 评审报告

### GUI 增强
- 动态 UI：不同模式显示不同控件
- 模式说明：每个选项都有即时文字说明
- 支持直接上传 .md 文件进行拆分
- 仅校对模式可选择来源模式决定提示词

## 开发指南

### 给新学科写 subject.py

最小实现（全部复用默认逻辑，只需指定工具）：

```python
from shared.sympy_tools.tools import EvaluateExpressionTool, SolveEquationTool
from core.defaults import (
    default_split_lecture, default_split_exam,
    default_proofread_one, default_collect_paper_dirs,
)

class SubjectApp:
    name = "高中数学"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self):
        return [EvaluateExpressionTool(), SolveEquationTool()]

    def get_max_tool_loops(self):
        return 20

    def get_tool_instructions(self):
        return "..."  # 工具使用说明，追加到提示词末尾

    def get_question_prompt(self):
        return self.config["question_prompt_lines"] + self.get_tool_instructions()

    def get_knowledge_prompt(self):
        return self.config["knowledge_prompt_lines"] + self.get_tool_instructions()

    def split_lecture(self, md_file, output_root, base_name, options):
        return default_split_lecture(md_file, output_root, base_name, options, self.config)

    # ... 其他方法同理
```

### 给新学科写 app.py

简单定制（继承默认模板，加几个控件）：

```python
from ui.default_app import DefaultApp
import tkinter as tk
from tkinter import ttk

class SubjectGui(DefaultApp):
    def setup_extra_options(self, frame):
        self.verify_original = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="原文联网校验",
                        variable=self.verify_original).pack(side=tk.LEFT)

    def on_start_proofread(self):
        self.subject_app.verify_original = self.verify_original.get()
        super().on_start_proofread()
```

完全自定义：从零搭建界面，只需通过 `self.subject_app` 调用业务逻辑即可。

## 相关文档

- [打包指南](docs/packaging.md) — PyInstaller 打包 + 便携 TeX 提取

## 版本

v2.1 — 学科独立架构 + 高中语文 v2.0 完整版（2026-06）
