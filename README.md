# 校对工具（学科独立版）

K-12 多学科 AI 校对工具集 —— 每个学科独立程序，深度定制业务逻辑和界面。**v3.0 全学科接入 ReAct 代理模式。**

## 架构理念

**每个学科是一个自治单元**，拥有独立的业务逻辑、UI 界面和配置。共享层（`core/`、`shared/`、`ui/`）只提供纯工具和默认模板，学科可自由复用或完全重写。

为什么这样设计？
- 各学科的拆分逻辑差异很大（有的按模块拆、有的按题目拆）
- 各学科的校对内容差异很大（如语文需要原文联网校验，其他学科不需要）
- 各学科的 UI 需求可能不同（有的需要额外开关、有的需要全新面板）
- 大部分学科尚未正式施工，架构必须预留最大灵活性

## 项目结构

```
JiaoDuiAgent/
├── core/                     # 纯工具层（零业务逻辑、零 UI）
│   ├── api_client.py         # API 调用（HTTP、重试、ReAct 工具循环）
│   ├── parsing.py            # LLM 输出解析（内联标记 + 结构化 JSON）
│   ├── defaults.py           # 默认拆分+校对参考实现
│   ├── base_subject.py       # SubjectApp 基类
│   ├── config_loader.py      # config.json + agent_prompt.json 加载
│   ├── config_schema.py      # 配置 Schema 验证
│   ├── format_enforcement.py # 格式审查（程序初筛 + LLM 修正）
│   ├── session_context.py    # 会话上下文封装
│   ├── pandoc_utils.py       # Pandoc 转换
│   ├── env_config.py         # .env 读写
│   ├── logging_utils.py      # 日志
│   ├── paths.py              # 路径工具（frozen 兼容）
│   └── manual_split.py       # 人工标记分割
├── shared/                   # 共享工具库
│   ├── sympy_tools/          # 符号计算工具集
│   ├── plan_tools.py         # ReAct 计划管理工具
│   ├── text_nav_tools.py     # ReAct 文本定位工具
│   ├── web_tools.py          # 联网检索
│   ├── smart_split.py        # 智能分割（LLM + XML标记）
│   ├── bash_tool.py          # Bash 命令执行工具
│   ├── chinese_classics_tools.py  # 文言文/诗歌校对
│   ├── shidianguji_playwright.py  # 识典古籍浏览器自动化
│   ├── docx_comments.py      # Word 批注提取
│   ├── docx_format_enhancer.py    # Word 格式标记增强
│   ├── review_mode.py        # 批注评审模式
│   ├── latex_generator.py    # Markdown → LaTeX
│   ├── pdf_compiler.py       # XeLaTeX PDF 编译
│   └── templates/
├── ui/                       # UI 组件库 + 默认模板
│   ├── widgets.py            # 可复用组件
│   └── default_app.py        # DefaultApp — 默认 GUI 模板
├── subjects/                 # 学科独立程序（7 学科）
│   ├── 高中语文v3.0/         # ReAct 范例学科
│   ├── 高中物理v3.0/
│   ├── 高中化学v3.0/
│   ├── 初中英语v3.0/
│   ├── 小学数学v3.0/
│   ├── 小学语文v3.0/
│   └── 高中历史v3.0/
├── tests/                    # 测试
├── tools/                    # 工具脚本（create_issues.py 等）
├── docs/                     # 文档
│   ├── adr/                  # 架构决策记录
│   ├── issues/               # Issue 文档
│   ├── notes/                # 杂项备忘
│   └── packaging.md          # 打包指南
├── memory/                   # 跨会话决策索引
├── specs/                    # PyInstaller spec 文件
├── requirements.txt
└── AGENTS.md                 # 项目工作约定
```

## 快速开始

### 环境要求

- Windows 10+
- Python 3.12
- Pandoc（Word 转 Markdown）
- TeX Live（可选，生成 PDF）

### 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 运行

```bash
# 各学科独立运行
python subjects/高中语文v3.0/main.py
python subjects/高中物理v3.0/main.py
# ...
```

## v3.0 核心特性：ReAct 代理模式

v3.0 将 LLM 从"一次性生成"升级为**自主规划-定位-校对**的代理模式：

| 能力 | 工具 | 说明 |
|------|------|------|
| 计划管理 | `plan_update` | 校对前声明步骤，进行中更新状态，完成后自检 |
| 文本定位 | `locate_paragraph` / `read_section` | 在长文中精确搜索和按范围读取文本 |
| 学科工具 | sympy / 联网搜索等 | 实算验证 + 专业术语检索 |
| 标注输出 | 内联标记 | 【编号\|原文\|改为】格式 |

**工作流**：声明计划 → 逐项执行 → 定位原文 → 验证证据 → 标记错误 → 全部完成自检输出

ReAct 模式通过 GUI 开关一键切换，关闭时回退到传统一次性校对模式。

## 三层分离架构

每个学科目录包含 3 个核心文件，职责清晰分离：

| 文件 | 职责 | 可否自定义 |
|------|------|-----------|
| `subject.py` | 业务逻辑（工具、提示词、拆分、校对、钩子） | ✅ 完全自定义或复用 `core/defaults` |
| `app.py` | GUI 界面 | ✅ 完全自定义或继承 `ui/default_app.DefaultApp` |
| `main.py` | 入口（组装 subject + app） | 基本不需要改 |

### 扩展方式

**添加一个新学科**：
1. 新建 `subjects/学科名/` 目录
2. 创建 `config.json`（提示词 + 拆分规则）
3. 创建 `agent_prompt.json`（ReAct 模式提示词）
4. 创建 `subject.py`：实现 `SubjectApp` 类
   - 工具集 → 覆盖 `build_tools()`
   - 调用次数 → 覆盖 `get_max_tool_loops()`
   - 工具指令 → 覆盖 `get_tool_instructions()`
   - 拆分逻辑 → 覆盖 `split_lecture()` / `split_exam()`
   - 校对钩子 → 覆盖 `pre/post_proofread_hook()`
   - 完全自定义校对 → 覆盖 `proofread_one()`
5. 创建 `app.py`：实现 `SubjectGui` 类
6. 创建 `main.py`：入口
7. `core/`、`shared/`、`ui/` **零改动**

## 已完成学科

| 学科 | 版本 | ReAct | 工具数 | 特色功能 |
|------|------|-------|--------|---------|
| 高中语文 | v3.0 | ✅ 范例 | 3（plan + navigate + 前置搜索） | 文言文/诗歌校验、批注评审、识典古籍 |
| 高中物理 | v3.0 | ✅ | 10（6 sympy + web_search + 3 ReAct） | 物理公式求解、量纲分析、向量运算 |
| 高中化学 | v3.0 | ✅ | 9（6 sympy + 3 ReAct） | 化学方程式配平、化学计量计算 |
| 小学数学 | v3.0 | ✅ | 7（4 sympy + 3 ReAct） | 算术验证、方程求解、五核校对 |
| 初中英语 | v3.0 | ✅ | 3（plan + navigate） | 词汇/语法/题型分层校对 |
| 小学语文 | v3.0 | ✅ | 3（plan + navigate） | 拼音/汉字/古诗词校对、IDML 支持 |
| 高中历史 | v3.0 | ✅ | 3（plan + navigate） | 史料辨析、时序判断、史论结合校对 |

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
| 智能分割 | 调用 LLM 自动识别题目边界 |
| 人工标记 | 按 `######` 手动标记拆分 |

## 开发指南

### 给新学科写 subject.py（v3.0 最低要求）

```python
from core.config_loader import load_config
from core.defaults import (
    default_split_lecture, default_split_exam,
    default_generate_knowledge, default_proofread_one,
    default_collect_paper_dirs,
)

class SubjectApp:
    name = "学科名"
    version = "v3.0"
    LEVEL = "学段"
    SUBJECT = "学科"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.react_mode = False          # 由 UI 控制
        self.tools = self.build_tools()

    def build_tools(self):
        base = []  # 学科专业工具
        if self.react_mode:
            from shared.plan_tools import PlanUpdateTool
            from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool
            base.extend([PlanUpdateTool(), LocateParagraphTool(), ReadSectionTool()])
        return base

    def get_max_tool_loops(self):
        return 15 if self.react_mode else 0

    def get_question_prompt(self):
        # ReAct 模式优先读取 agent_prompt.json
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                return "\n".join(agent_lines)
        return "\n".join(self.config.get("question_prompt_lines", []))

    # proofread_one 签名必须一致:
    def proofread_one(self, api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf, source_mode="试卷"):
        ...
        return default_proofread_one(..., react_mode=self.react_mode)
```

## 相关文档

- [打包指南](docs/packaging.md) — PyInstaller 打包 + 便携 TeX 提取
- [架构决策记录](docs/adr/) — 各版本关键技术决策

## 版本

v3.0 — 全学科 ReAct 代理模式接入（2026-06）
