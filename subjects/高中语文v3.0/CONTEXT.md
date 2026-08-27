# 高中语文校对

高中语文学科的校对工具，支持文言文、诗歌、现代文等多种题型的智能校对。

## 语言

**校对单元**：
送进 LLM 进行一次校对的最小内容块。可以是一道小题、一篇文章加几道小题、一首诗加鉴赏题等。

**自由校对模式**：
用户可以粘贴文本+图片或上传文件，灵活选择是否拆分、用什么方式拆分的校对模式，不依赖固定的讲义/试卷格式。

**智能分割**：
调用 LLM 自动识别文档中的完整题目单元，用 `<problem>` 标签标记边界，替代传统的规则分割。

**前置原文搜索**：
在校对之前，程序自动识别文言文/诗歌内容，主动到识典古籍/搜韵网检索原文，作为参考提供给 LLM。

**自动差异比对**：
程序拿到原文后，自动做字符级 diff，找出所有字面差异，再交给 LLM 判断哪些是真正的错误。

**识典古籍**：
https://www.shidianguji.com/ ，古籍全文检索网站，用于文言文原文比对。

**搜韵网**：
https://sou-yun.cn/ ，古诗词检索网站，用于诗歌原文比对。

_Alias_: 搜韵

## 校对数据流

整个校对管线有两条主要路径——**普通校对**（讲义/试卷/自由校对）和**批注评审**——它们在 LLM 输出格式和报告渲染时有差异，但共享同一套解析和报告生成基础设施。

### 阶段一：转换（.docx → .md）

```
Word .docx
  ├─ Pandoc 转换 → raw.md（Markdown 正文 + 图片提取）
  ├─ enhance_docx_conversion() → 注入格式标记
  │     【着重】...【/着重】  【下划线】...【/下划线】
  │     【波浪线】...【/波浪线】  【删除线】...【/删除线】
  └─ insert_comments_from_docx() → 注入批注标记（仅批注评审模式）
        [📝批注1：原批注内容]  [📝批注2：原批注内容]
```

### 阶段二：拆分（raw.md → 第N题/）

raw.md 按标题或题号拆分为子目录，每题目录含：
- `第N题.md` — 含批注标记和格式标记的正文
- `第N题_clean.md` — 去除所有标记的纯净版（供 LLM 阅读）
- `images/` — 本题目配图

### 阶段三：LLM 校对

**普通校对路径** — LLM 输出标准内联格式：
```
### 标记原文
[逐字抄写全文，错误处插入 【1|原文字段|修改后文字】 【2|...|...】]

### 修改原因
1. 原因
2. 原因
```

**批注评审路径** — LLM 输出混合格式：
```
## 批注评审结果

### 批注1
- 评判：正确 / 部分正确 / 有误
- 说明：理由

### 批注2
...

### 补充发现

### 标记原文
[逐字抄写全文，遗漏错误处插入 【1|原文字段|修改后文字】]

### 修改原因
1. 原因
```

### 阶段四：解析（LLM 文本 → _校对数据.json）

`save_proofread_json()` 并行运行两个解析器：

| 解析器 | 文件:函数 | 识别的格式 | 产出字段 |
|---|---|---|---|
| `parse_proofread_md` | `core/parsing.py:127` | `### 标记原文` + `【N\|原文\|改为】` | `corrections`, `marked_text`, `summary` |
| `parse_review_result` | `shared/review_mode.py:108` | `### 批注N` / `评判` / `说明` / `### 补充发现` | `review_judgments`, `review_supplements` |

两者结果合并存入同一 JSON。普通校对只有 `corrections`，批注评审两者都有。

### 阶段五：排版（Word 批注报告）

LaTeX/PDF 排版已下线（ADR-0030），排版输出仅剩 Word 批注报告：

`generate_combined_docx()`（`core/docx_report.py`）合并各题 `_校对报告.md` → pandoc 转 docx（`$...$` 数学记法经 texmath 转 Word 原生公式）→ zipfile 级注入批注（`comments.xml`）：

- 正文公式 → Word 原生公式（OMML）；批注内公式 → `shared/formula_render.py`（matplotlib）渲染 PNG 嵌入，失败降级为文本
- 批注注入：`shared/docx_comments.py` 解析 `【N|原|改】` 标记 → `w:commentRangeStart/End` + `w:comment`，格式标记（着重/下划线等）由 `shared/docx_format_enhancer.py` 处理

### 关键文件索引

| 文件 | 职责 |
|---|---|
| `core/parsing.py` | LLM 输出解析，双格式回退 |
| `core/defaults.py` | 默认校对流程 + 转换后格式增强 |
| `shared/review_mode.py` | 批注提取、评审 prompt、评审结果解析 |
| `core/docx_report.py` | 合并各题报告 → Word 批注版 docx |
| `shared/docx_comments.py` | Word 批注提取与注入 |
| `shared/docx_format_enhancer.py` | Word 特殊格式提取与注入 |
| `shared/formula_render.py` | 批注内公式渲染（matplotlib → PNG） |
| `ui/default_app.py` | 主调度器：转换→拆分→校对→Word |
