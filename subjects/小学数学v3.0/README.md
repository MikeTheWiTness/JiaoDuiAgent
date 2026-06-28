# 小学数学校对工具 v3.0

AI 驱动的小学数学题目校对工具 —— Word 转 Markdown → 智能拆分 → ReAct 代理校对 → 符号计算实算验证 → 校对报告生成

## v3.0 新特性：ReAct 代理模式

LLM 能够**自主规划、定位原文、调用数学工具验证**，而非一次性生成：

| 能力 | 工具 | 说明 |
|------|------|------|
| 计划管理 | `plan_update` | 声明步骤 → 逐项执行 → 自检输出 |
| 文本定位 | `locate_paragraph` / `read_section` | 精确搜索定位原文中的题号和算式 |
| 算术验证 | `evaluate_expression` | 所有算术计算必须调用此工具实算 |
| 方程求解 | `solve_equation` | 一元一次方程、比例方程、简单方程组 |
| 等价判断 | `check_equality` | 验证化简结果与答案表达式等价性 |
| 表达式化简 | `simplify_expression` | 分数约分、代数式化简、展开、因式分解 |

ReAct 模式通过 GUI 开关一键切换。

## 功能特点

- **格式转换**：Word `.docx` → Markdown
- **智能拆分**：支持普通规则 / 不拆分 / 智能分割 / 人工标记
- **ReAct AI 校对**：LLM 自主规划校对步骤，工具实算验证
- **逐题五核校对**：题干可做性 → 答案独立复核 → 解析逻辑核对 → 配图表格核对 → 排版规范性
- **PDF 报告**：LaTeX 双栏对照排版
- **批量处理 + 中断恢复**

## 快速开始

```bash
cd JiaoDuiAgent
pip install -r requirements.txt
python subjects/小学数学v3.0/main.py
```

## 工具说明

| 工具 | 类型 | 说明 |
|------|------|------|
| `plan_update` | ReAct | 校对计划管理 |
| `locate_paragraph` | ReAct | 关键词搜索定位 |
| `read_section` | ReAct | 按行号范围读取 |
| `evaluate_expression` | 符号计算 | 算术计算（加减乘除、分数、小数、百分数） |
| `solve_equation` | 符号计算 | 方程求解（一元一次、比例方程、简单方程组） |
| `check_equality` | 符号计算 | 等价判断（验证化简/变形正确性） |
| `simplify_expression` | 符号计算 | 表达式化简（约分、展开、因式分解） |

ReAct 模式工具调用上限 15 轮，非 ReAct 模式 10 轮。单位换算也必须调用工具验证。

## 校对范围

1. 题干可做性：错别字、数字单位条件完整性、年级认知匹配
2. 答案独立复核：强制独立重算，不盲信原答案
3. 解析逻辑：步骤完整性、逻辑自洽、结论与答案一致
4. 配图表格：图片/竖式/统计图准确性、表格完整性
5. 排版规范：标点、单位标注、公式排版、填空横线

## 目录结构

```
小学数学v3.0/
├── main.py / subject.py / app.py
├── config.json          # 提示词 + 拆分规则
├── agent_prompt.json    # ReAct 模式提示词
└── .env
```
