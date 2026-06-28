# ADR 0004：识典古籍 Playwright 集成与正文精确截取

**状态**：已接受
**日期**：2026-06-26
**决策者**：MikeTheWiTness
**相关 ADR**：[[ADR 0003 三层校对架构]](memory/shidianguji-text-extraction.md)

---

## 背景

当前文言文校对的前置搜索链路（ddgs → web_fetch → 第三方网站提取原文）存在两个核心问题：

1. **识典古籍正文无法抓取**：识典古籍（shidianguji.com）是当前最权威的古籍数字化平台，但其详情页为 React SPA，服务端 `_SSR_DATA.data` 为空，正文仅在浏览器执行 JS 后渲染。现有纯 HTTP 抓取方案（`requests.get` + 正则）完全无法拿到正文。
2. **搜索返回全文与试卷节选不匹配**：搜索定位到章节后，全文可能长达数千字（如韦凑传 1197 字），而试卷上只节选了其中约 600 字。程序 diff 需要定位节选在全文中的精确区间，否则 diff 结果全是噪音。

此外，还有两个前置工程问题需要修复：

3. **`_clean.md` 与 raw 版共存问题**：Word 转 MD 后产生带格式标记的 `_raw.md`，但校对前需要一份去除所有标记的干净版本做原文比对。如果按题目目录中放两份 `.md`，当前 `default_proofread_one` 的读取逻辑（取第一个 `.md`）会读错文件。
4. **校对入口 `default_proofread_one` 的文件选择逻辑脆弱**：它通过 `os.listdir` + `break` 选取第一个 `.md` 文件，依赖文件系统返回顺序，不检查文件名与目录名是否一致。

## 决策

### 决策 1：Playwright 作为识典古籍正文提取的优先方案

**选择**：Playwright headless Chromium 渲染识典详情页 → 从 `article.chapter-reader` DOM 提取正文。

**理由**：
- 已验证可行（韦凑传实测：29 段、1197 字，精确提取）
- 项目 venv 已安装 Playwright 1.60 + Chromium 1223
- `wait_until="domcontentloaded"` + 等 `article.chapter-reader p` 即可稳定提取
- 新建独立模块 `shared/shidianguji_playwright.py`，软依赖——Playwright 不可用时静默回退到现有 ddgs 链路

**备选方案**：
- **继续用 ddgs + 第三方网站**：已有但质量不可控，第三方网站可能下线或改版
- **逆向后端 API**：JS 混淆严重，接口可能随时变化，维护成本高

### 决策 2：difflib 双锚点精确截取节选范围

**选择**：去除所有标点后，用 `difflib.SequenceMatcher` 对齐全文与节选，保留匹配区间的两端各 `margin=20` 字上下文。

**理由**：
- 已验证：韦凑传 1197 字全文 vs 593 字节选 → **98.7% 匹配率**（471/477 去标点字），差异仅在家世背景（34 字）、跳过的奏对段落（448 字）、结尾追赠（11 字）及 6 处单字异文
- "可多不可少"——保留 margin 确保不会因为截断而漏掉节选边缘文字
- 截取后 diff 结果直接反映"权威原文 vs 待校稿"的精确差异，AI 可判断真错 vs 异文

### 决策 3：生成独立的 `_clean.md` 文件

**选择**：在 pandoc 转换阶段生成两份 MD：
- `_raw.md`：含格式标记（用于后期排版）
- `_clean.md`：完全去除标记的纯文本（用于原文对照和搜索）

**理由**：
- 避免每次搜索/比对时重复执行 `_clean_annotations()` + `strip_format_markers()`
- clean 版只在转换环节生成一次，切分时随 raw 版一起分发到各题目目录
- 后续校对逻辑可选择读取 `_clean.md` 做前置处理

### 决策 4：修复 `default_proofread_one` 的文件选择逻辑

**选择**：精确匹配目录名，只读取 `{q_dir}/{q_name}.md`，不再遍历所有 `.md` 文件。

**理由**：
- 目录中会有 `第1题.md` + `第1题_clean.md` 两个 md 文件，现有逻辑会随机挑一个
- 精确匹配后，`_clean.md`、`_校对报告.md` 等辅助文件不会干扰读取

## 架构影响

### 新增模块

```
shared/shidianguji_playwright.py  ← Playwright 搜索+抓取封装
   ├─ is_playwright_available()   → True/False
   ├─ extract_chapter(book_id, chapter_id) → {title, text}
   └─ search_and_extract(keywords) → 完整原文文本
```

### 修改模块

```
core/pandoc_utils.py
   └─ convert_with_pandoc() → 生成 _clean.md

subjects/高中语文v3.0/subject.py
   └─ _write_problems_to_dirs() → 同步写 _clean.md

core/defaults.py
   └─ default_proofread_one() → 精确文件名匹配

shared/chinese_classics_tools.py
   ├─ search_original_text() → 识典优先（Playwright 可用时）
   ├─ 新增 extract_excerpt_from_full()  → 节选范围截取
   └─ preprocess_for_proofread() → 适配 _clean.md
```

### 数据流（优化后）

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
        ├─ 精确读取 第1题/第1题.md → 含标记版（给 LLM 排版用）
        ├─ 精确读取 第1题/第1题_clean.md → 干净版（搜索+比对用）
        ├─ 取前 10 字 → 识典搜索（Playwright 优先）
        ├─ difflib 截取节选范围 → 机器 diff
        ├─ 0 差异 → 跳过文言文 LLM 校验
        └─ 有差异 → 参考段注入 prompt，发 LLM
```

## 后果

### 正面
- 识典古籍成为自动化可用的权威来源
- 节选区间精确匹配，diff 只反映真实差异
- `_clean.md` 分离了"排版"与"比对"两个关注点
- Playwright 不可用时无缝回退，不影响现有部署

### 负面
- 增加 Playwright 依赖（约 300MB Chromium），但为可选
- 单次识典抓取耗时约 2-5 秒（headless browser 渲染），比纯 HTTP 慢
- 每个题目目录多一个 `_clean.md` 文件（体积很小）

### 风险
- 识典古籍前端 DOM 结构可能变化（低概率，识典是字节跳动维护的稳定产品）
- Playwright 与 Chromium 版本需匹配（`playwright install chromium` 可解决）
