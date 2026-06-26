---
name: 识典古籍文本提取方案
description: 前置搜索 → 程序 diff → LLM 判断的三层架构，以及识典古籍 SPA 抓取难题
metadata:
  type: project
---

# 文言文/诗歌前置搜索方案

## 目标

在校对高中语文试卷中的文言文/诗歌题目时，**程序先自动搜索权威原文并做字符级 diff**，把结果注入 prompt，让 AI 直接判断差异而无需自己反复搜索。

## 三层架构（ADR 0003）

```
第一层（程序前置搜索）  →  第二层（程序字符 diff）  →  第三层（LLM 判断）
搜索权威来源拿到原文      逐字比对，列出所有差异     AI 判断哪些是真错误
```

## ADR 0004（2026-06-26）——识典古籍 Playwright 集成

[[../docs/adr/0004-shidianguji-playwright-integration]]

### 核心发现

1. **搜索页**：纯 HTTP `requests.get` 即可拿到 `/book/xxx/chapter/xxx` 链接（`_parse_shidianguji_search` 已有实现）
2. **详情页**：React SPA，服务端 `_SSR_DATA.data` 为空 `{}`，正文仅在 JS 渲染后出现在 `article.chapter-reader` DOM 中
3. **Playwright 实测通过**：韦凑传 29 段 1197 字精确提取，`wait_until="domcontentloaded"` + 等 `article.chapter-reader p`（不能用 `networkidle`——统计心跳导致超时）
4. **difflib 对齐**：韦凑传全文 1197 字 vs 节选 593 字 → 98.7% 匹配率，差异仅在家世背景、跳过段落、异体字

### 决策

- **Playwright 优先**：识典可用时从识典提取，不可用时回退 ddgs
- **difflib 截取**：从全文精确定位节选区间，"可多不可少"
- **独立 `_clean.md`**：转换阶段生成两份 MD，避免每次搜索时重复清洗标记
- **精确文件名匹配**：`default_proofread_one` 改为匹配目录名，不再 `os.listdir` + `break`

### Issue 状态（2026-06-26 全部完成）

| # | 标题 | 提交 | 状态 |
|---|------|------|------|
| #1 | 修复 default_proofread_one 文件选择逻辑 | `fedcea8` | ✅ 完成 |
| #2 | `_clean.md` 全链路生成 | `f417d9d` | ✅ 完成 |
| #3 | Playwright 识典古籍提取模块 | `131e265` | ✅ 完成 |
| #4 | difflib 节选精确截取算法 | `094d3ab` | ✅ 完成 |
| #5 | 端到端识典集成进校对链路 | `688ec4b` | ✅ 完成 |

**全部 65 个测试通过，回归零破坏。**

### 优化后完整数据流

```
Word (.docx)
  │
  ├─① pandoc → _raw.md（含【下划线】等标记）
  │         └→ _clean.md（新增，完全干净）
  │
  ├─② smart_split（输入 _raw.md）→ 第1题/第1题.md
  │                               → 第1题/第1题_clean.md（新增）
  │
  └─③ proofread_one(第1题/)
        ├─ 精确读取 第1题/第1题.md → 含标记版（给 LLM）
        ├─ 精确读取 第1题/第1题_clean.md → 干净版（搜索用）
        ├─ 取前 10 字 → 识典搜索（Playwright 优先，不可用则 ddgs）
        ├─ difflib 截取节选范围（可多不可少） → 机器 diff
        ├─ 0 差异 → 标记一致，LLM 指令跳过文言文逐字校对
        └─ 有差异 → 差异列表注入 prompt，LLM 判断真错 vs 异文
```

## 相关文件

- [[chinese-classics-tools]]
- [[proofread-hook-integration]]
