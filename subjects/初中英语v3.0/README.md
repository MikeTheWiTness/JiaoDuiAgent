# 初中英语校对工具 v3.0

AI 驱动的初中英语题目校对工具 —— Word 转 Markdown → 智能拆分 → ReAct 代理校对 → 校对报告生成

## v3.0 新特性：ReAct 代理模式

LLM 能够**自主规划、定位原文、逐项校对**，而非一次性生成：

| 能力 | 工具 | 说明 |
|------|------|------|
| 计划管理 | `plan_update` | 声明步骤 → 逐项执行 → 自检输出 |
| 文本定位 | `locate_paragraph` / `read_section` | 精确搜索定位原文中的词汇/语法/阅读段落 |

ReAct 模式通过 GUI 开关一键切换。

## 功能特点

- **格式转换**：Word `.docx` → Markdown（支持讲义 section 模式拆分）
- **智能拆分**：支持普通规则 / 不拆分 / 智能分割 / 人工标记
- **ReAct AI 校对**：LLM 自主规划校对步骤
- **分层校对**：按版块类型自动适用校对规则（词汇/语法/题型训练/巩固练习）
- **PDF 报告**：LaTeX 双栏对照排版
- **批量处理 + 中断恢复**

## 快速开始

```bash
cd JiaoDuiAgent
pip install -r requirements.txt
python subjects/初中英语v3.0/main.py
```

## 工具说明

| 工具 | 类型 | 说明 |
|------|------|------|
| `plan_update` | ReAct | 校对计划管理 |
| `locate_paragraph` | ReAct | 关键词搜索定位 |
| `read_section` | ReAct | 按行号范围读取 |

英语以语法/词汇/阅读的文字校对为主，无需计算工具。

## 校对范围（按版块分层）

**词汇版块**：音标准确性、词形变化、词义与搭配、易混词辨析

**语法版块**：语法规则表述、例句正确性、练习题答案、填空选择题

**题型训练/巩固练习**：题目设计、选项分析、答案解析

忽略英美拼写差异（color/colour 等不视为错误）。

## 目录结构

```
初中英语v3.0/
├── main.py / subject.py / app.py
├── config.json          # 提示词 + 拆分规则（含 section 模式）
├── agent_prompt.json    # ReAct 模式提示词
└── .env
```
