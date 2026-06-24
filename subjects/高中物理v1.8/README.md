# 高中物理校对工具

AI 驱动的高中物理题目校对工具 —— Word 转 Markdown → 智能拆分 → 符号计算实算验证 → 校对报告生成

## 功能特点

- **格式转换**：Word `.docx` → Markdown（Pandoc，保留 LaTeX 数学公式）
- **智能拆分**：按粗体标题标记拆为独立单题，自动提取知识部分
- **AI 校对**：调用 LLM API（`reasoning_effort: high`），支持符号计算工具实算验证
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
- TeX Live（可选，用于生成 PDF 报告；不装也能校对，只是不能生成 PDF）

### 安装依赖

```bash
cd 校对agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 运行

```bash
python 高中物理/main.py
```

### 使用步骤

1. 点击 **⚙️ API 配置** 填写接口地址、密钥和模型名（自动保存到 `高中物理/.env`）
2. 选择文档**来源**（讲义/试卷）和**执行模式**
   - 完整流程：转换 + 拆分 + 校对
   - 仅拆分：只转 Word + 拆题
   - 仅校对：对已有拆分结果校对
   - 仅生成 PDF：从已有校对结果生成 PDF 报告
3. 添加 Word 文件，点击**开始处理**

## 工具说明

高中物理使用以下 7 个 AI 工具（校对时 LLM 可调用）：

| 工具 | 说明 |
|------|------|
| `evaluate_expression` | 数值表达式求值（含三角函数、对数等） |
| `solve_equation` | 方程/方程组求解 |
| `solve_physics_formula` | 物理公式代入求值 |
| `dimensional_analysis` | 量纲分析 |
| `vector_operations` | 向量运算（加减、点乘、叉乘、模） |
| `circle_from_two_points` | 由两点求圆的方程（磁场偏转题用） |
| `web_search` | 联网搜索补充信息 |

工具调用上限 20 轮，超限自动降级为无工具模式重试。

## 目录结构

```
高中物理/
├── main.py             # 入口
├── subject.py          # 业务逻辑（工具、提示词、拆分、校对）
├── app.py              # GUI（继承默认模板）
├── config.json         # 配置（提示词 + 拆分规则）
└── .env                # API 配置（运行时生成）
```

## 配置说明

### config.json

```json
{
  "question_prompt_lines": ["..."],
  "knowledge_prompt_lines": ["..."],
  "lecture_split": {
    "split_mode": "title",
    "wrapped_patterns": ["例\\d+", "练\\d+"],
    "unwrapped_patterns": [],
    "section_boundary": true
  },
  "exam_split": {
    "question_pattern": "^(\\d+)．"
  }
}
```

- `question_prompt_lines`：题目校对提示词
- `knowledge_prompt_lines`：知识部分校对提示词
- `lecture_split.split_mode`：讲义拆分模式（`title` 按标题拆 / `section` 按章节拆）
- `exam_split.question_pattern`：试卷题号正则

### .env

```
API_URL=https://ark.cn-beijing.volces.com/api/v3
API_KEY=your-api-key
MODEL_NAME=doubao-seed-2-0-pro-260215
```

通过 GUI 的「API 配置」按钮自动维护，无需手动编辑。

## 数据流

```
.docx 文件
  → Pandoc → 原始 .md（+ images/）
  → LaTeX 转义修复 / 后处理（浮空图片修正 + 空格压缩）
  → 拆分：
      讲义 title 模式 → 第N题/第N题.md + images/ + 知识/
      试卷模式     → 第N题/第N题.md + images/
  → AI 校对（物理提示词 + 7个工具 + reasoning_effort=high）
  → _校对报告.md + _校对数据.json
  → LaTeX 双栏 PDF（可选）
```

## 打包为 EXE

详见 [docs/packaging.md](../docs/packaging.md)。

```bash
# 1. 提取便携 TeX（首次或 TeX 更新时）
python tools/build_minimal_texlive.py

# 2. 打包
pip install pyinstaller
pyinstaller specs/高中物理.spec
```

输出在 `dist/高中物理/`。
