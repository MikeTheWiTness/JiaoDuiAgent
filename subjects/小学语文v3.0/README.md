# 小学语文校对工具 v3.0

AI 驱动的小学语文题目校对工具 —— Word 转 Markdown → 智能拆分 → ReAct 代理校对 → 校对报告生成

## v3.0 新特性：ReAct 代理模式

LLM 能够**自主规划、定位原文、逐项校对**，而非一次性生成：

| 能力 | 工具 | 说明 |
|------|------|------|
| 计划管理 | `plan_update` | 声明步骤 → 逐项执行 → 自检输出 |
| 文本定位 | `locate_paragraph` / `read_section` | 精确搜索定位原文中的字词和段落 |

ReAct 模式通过 GUI 开关一键切换。

## 功能特点

- **格式转换**：Word `.docx` / InDesign `.idml` → Markdown
- **智能拆分**：支持普通规则 / 不拆分 / 智能分割 / 人工标记
- **ReAct AI 校对**：LLM 自主规划校对步骤
- **拼音/汉字/古诗词**：覆盖小学语文全维度校对需求
- **IDML 支持**：支持 InDesign 导出的 IDML 文件直接提取
- **PDF 报告**：LaTeX 双栏对照排版
- **批量处理 + 中断恢复**

## 快速开始

```bash
cd JiaoDuiAgent
pip install -r requirements.txt
python subjects/小学语文v3.0/main.py
```

## 工具说明

| 工具 | 类型 | 说明 |
|------|------|------|
| `plan_update` | ReAct | 校对计划管理 |
| `locate_paragraph` | ReAct | 关键词搜索定位 |
| `read_section` | ReAct | 按行号范围读取 |

## 校对范围

1. 文字校对：错别字、漏字、多字、标点符号、字形错误
2. 图片校对：图片缺失、配图与题目一致性
3. 拼音校对：声母、韵母、声调标注
4. 汉字书写：笔顺、偏旁部首、间架结构
5. 词语运用：近义词辨析、成语使用、词语搭配
6. 句子练习：句式转换、病句修改、仿写句子
7. 阅读理解：文本引用准确性、题干表述清晰度
8. 古诗词：诗句引用完整性、注释正确性
9. 写作题：材料理解、立意引导
10. 答案校验：答案与题干匹配、解析逻辑自洽

## 支持的文件格式

- Word 文档：`.docx` `.doc`
- InDesign IDML：`.idml`
- Markdown：`.md`
- ZIP 压缩包

## 目录结构

```
小学语文v3.0/
├── main.py / subject.py / app.py
├── config.json          # 提示词 + 拆分规则
├── agent_prompt.json    # ReAct 模式提示词
└── .env
```
