# 高中化学校对工具 v3.0

AI 驱动的高中化学题目校对工具 —— Word 转 Markdown → 智能拆分 → ReAct 代理校对 → 化学方程式配平验证 → 校对报告生成

## v3.0 新特性：ReAct 代理模式

LLM 能够**自主规划、定位原文、调用化学计算工具验证**，而非一次性生成：

| 能力 | 工具 | 说明 |
|------|------|------|
| 计划管理 | `plan_update` | 声明步骤 → 逐项执行 → 自检输出 |
| 文本定位 | `locate_paragraph` / `read_section` | 精确搜索定位原文中的化学方程式和文字 |
| 化学计算 | `balance_chemical_equation` `stoichiometry_calc` 等 | 配平验证、计量计算，禁止凭经验 |
| 符号计算 | `evaluate_expression` `solve_equation` 等 | 数值计算必调工具实算 |

ReAct 模式通过 GUI 开关一键切换。

## 功能特点

- **格式转换**：Word `.docx` → Markdown（Pandoc，保留化学式排版）
- **智能拆分**：支持普通规则 / 不拆分 / 智能分割 / 人工标记
- **ReAct AI 校对**：LLM 自主规划校对步骤，化学计算工具实算验证
- **化学专用工具**：化学方程式配平、化学计量计算
- **PDF 报告**：LaTeX 双栏对照排版
- **批量处理 + 中断恢复**

## 快速开始

```bash
cd JiaoDuiAgent
pip install -r requirements.txt
python subjects/高中化学v3.0/main.py
```

## 工具说明

| 工具 | 类型 | 说明 |
|------|------|------|
| `plan_update` | ReAct | 校对计划管理 |
| `locate_paragraph` | ReAct | 关键词搜索定位 |
| `read_section` | ReAct | 按行号范围读取 |
| `balance_chemical_equation` | 化学 | 配平化学方程式（反应物 -> 产物） |
| `stoichiometry_calc` | 化学 | 化学计量计算（质量→质量） |
| `evaluate_expression` | 符号计算 | 数值表达式求值 |
| `solve_equation` | 符号计算 | 方程求解（平衡常数、pH等） |
| `check_equality` | 符号计算 | 表达式等价验证 |
| `simplify_expression` | 符号计算 | 表达式化简 |

ReAct 模式工具调用上限 20 轮，非 ReAct 模式 15 轮。

## 校对范围

1. 文字校对：错别字、漏字、多字、标点符号
2. 化学用语：化学式大小写、方程式配平、离子方程式电荷守恒、热化学方程式 ΔH
3. 符号与单位：元素符号、化合价、化学计量单位
4. 选择题：选项严谨性、正确答案唯一性
5. 大题专项：实验题/工业流程题/推断题/计算题
6. 解析审核：解题逻辑、化学原理引用、计算过程
7. 答案校验：数值/文字/方程式类答案正确性

## 目录结构

```
高中化学v3.0/
├── main.py / subject.py / app.py
├── config.json          # 提示词 + 拆分规则
├── agent_prompt.json    # ReAct 模式提示词
└── .env
```
