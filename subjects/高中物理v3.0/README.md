# 高中物理校对工具 v3.0

AI 驱动的高中物理题目校对工具 —— Word 转 Markdown → 智能拆分 → ReAct 代理校对 → 符号计算实算验证 → 校对报告生成

## v3.0 新特性：ReAct 代理模式

LLM 能够**自主规划、定位原文、调用工具验证**，而非一次性生成校对结果：

| 能力 | 工具 | 说明 |
|------|------|------|
| 计划管理 | `plan_update` | 声明步骤 → 逐项执行 → 自检输出 |
| 文本定位 | `locate_paragraph` / `read_section` | 精确定位长文中的目标段落 |
| 符号计算 | `evaluate_expression` `solve_equation` `solve_physics_formula` 等 | 实算验证，禁止凭经验 |
| 联网搜索 | `web_search` | 检索最新物理术语、不在训练数据内的信息 |

ReAct 模式通过 GUI 开关一键切换，关闭时回退到传统一次性校对模式。

## 功能特点

- **格式转换**：Word `.docx` → Markdown（Pandoc，保留 LaTeX 数学公式）
- **智能拆分**：支持普通规则 / 不拆分 / 智能分割 / 人工标记 四种拆分方式
- **ReAct AI 校对**：LLM 自主规划校对步骤，支持符号计算工具实算验证
- **符号计算工具**：表达式求值、方程求解、物理公式求解、量纲分析、向量运算、圆的方程
- **联网搜索**：支持联网检索补充信息
- **PDF 报告**：LaTeX 双栏对照排版（左栏原题 + 红色圈号标记，右栏修改建议）
- **批量处理**：支持多文件批量转换 + 多题并行校对
- **中断恢复**：已校对题目自动跳过，支持中断后继续

## 快速开始

### 环境要求

- Windows 10+
- Python 3.12
- Pandoc（用于 Word 转换）
- TeX Live（可选，用于生成 PDF 报告）

### 安装依赖

```bash
cd JiaoDuiAgent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 运行

```bash
python subjects/高中物理v3.0/main.py
```

### 使用步骤

1. 点击 **⚙️ API 配置** 填写接口地址、密钥和模型名（自动保存到 `.env`）
2. 选择文档**来源**（讲义/试卷/自由校对/批注评审）和**执行模式**
3. 开启 **ReAct 模式** 以获得更准确的校对结果
4. 添加 Word 文件，点击**开始处理**

## 工具说明

高中物理使用以下 10 个 AI 工具（校对时 LLM 可调用）：

| 工具 | 类型 | 说明 |
|------|------|------|
| `plan_update` | ReAct | 校对计划管理（声明/更新/完成） |
| `locate_paragraph` | ReAct | 关键词搜索定位原文段落 |
| `read_section` | ReAct | 按行号范围读取原文 |
| `evaluate_expression` | 符号计算 | 数值表达式求值（含三角函数、对数等） |
| `solve_equation` | 符号计算 | 方程/方程组求解 |
| `solve_physics_formula` | 符号计算 | 物理公式代入求值 |
| `dimensional_analysis` | 符号计算 | 量纲分析 |
| `vector_operations` | 符号计算 | 向量运算（加减、点乘、叉乘、模） |
| `circle_from_two_points` | 符号计算 | 由两点求圆的方程（磁场偏转题用） |
| `web_search` | 联网 | 联网搜索补充信息 |

ReAct 模式工具调用上限 25 轮，非 ReAct 模式 20 轮，超限自动降级重试。

## 目录结构

```
高中物理v3.0/
├── main.py             # 入口
├── subject.py          # 业务逻辑（工具、提示词、拆分、校对）
├── app.py              # GUI（继承默认模板）
├── config.json         # 配置（提示词 + 拆分规则）
├── agent_prompt.json   # ReAct 模式提示词
├── .env                # API 配置（运行时生成）
└── README.md
```

## 配置说明

### config.json

```json
{
  "question_prompt_lines": ["..."],
  "knowledge_prompt_lines": ["..."],
  "lecture_split": { "wrapped_patterns": ["例\\d+", ...], "section_boundary": true },
  "exam_split": { "question_pattern": "^(\\d+)．" }
}
```

### agent_prompt.json

ReAct 模式专用提示词，包含学科身份定义、可用工具说明、校对流程、工具使用规则和强制返回格式。

### .env

```
API_URL=https://ark.cn-beijing.volces.com/api/v3
API_KEY=your-api-key
MODEL_NAME=doubao-seed-2-0-pro-260215
```

通过 GUI 的「API 配置」按钮自动维护。

## 数据流

```
.docx 文件
  → Pandoc → 原始 .md（+ images/）
  → LaTeX 转义修复 / 后处理
  → 拆分：规则/不拆分/智能/人工 → 第N题/第N题.md + 第N题_clean.md + images/
  → 前置处理 hook（文言文/诗歌搜索）
  → ReAct AI 校对（plan → locate → verify → mark）
  → _校对报告.md + _校对数据.json + _API对话记录.md
  → LaTeX 双栏 PDF（可选）
```

## 打包为 EXE

详见 [docs/packaging.md](../../docs/packaging.md)。

```bash
python tools/build_minimal_texlive.py    # 1. 提取便携 TeX
pyinstaller specs/高中物理.spec          # 2. 打包
```
