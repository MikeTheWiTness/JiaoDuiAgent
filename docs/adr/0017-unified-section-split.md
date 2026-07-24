# ADR 0017：统一规则拆分 —— section 模式 + 单元命名 + 废弃知识提取

**状态**：已实现（commit 9bf087a）
**日期**：2026-07-07
**实现日期**：2026-07-09
**决策者**：MikeTheWiTness
**关联**：[[ADR 0015 统一校对流程]](0015-unified-proofread-flow.md)

---

## 背景

当前讲义拆分存在两套逻辑：

**title 模式**（语文/物理/化学/生物/英语/数学，7 个学科）：
- 按题目标记（`**例1**`、`**练1**` 等）切分为 `第N题/` 目录
- 题目之间的过渡文本（知识讲解）被过滤出来，单独写入 `知识/` 文件夹
- 题目和知识是**两级分离结构**

**section 模式**（仅高中历史）：
- 按标题切分（`## 模块`、`**例1**`、`### 模型大招` 等），输出统一 `板块N/` 目录
- 不区分"题目"和"知识"——每个板块是连续的内容块
- 知识和题目**平等对待**，都是切分边界

title 模式的问题：
1. 知识提取依赖 `generate_knowledge`，按 `wrapped_patterns` 过滤行——容易漏掉或错误归类
2. 知识文件夹脱离原始顺序，审核时需要在题目和知识之间来回跳转
3. 两种不同的目录命名（`第N题/` + `知识/`）增加下游复杂度

---

## 决策

### 决策 1：所有学科统一使用 section 模式

`default_split_lecture` 的默认 `split_mode` 从 `"title"` 改为 `"section"`。

**默认 section_pattern**（内置常量，学科无需重复配置）：

```
^#{2,3}\s                      # ## / ### Markdown 标题
|\*\*(例|练|变式|真题)\d+\*\*    # **例1**、**练1**、**变式1**、**真题1**
|\*\*教师版\*\*                 # **教师版**
|必备知识                        # 知识章节标题
|模型大招                        # 方法/模型总结标题
|重难点突破                      # 重难点专题标题
```

最后三项（`必备知识|模型大招|重难点突破`）作为通用扩展，覆盖所有学科的常见知识标题模式。

### 决策 2：统一命名为 `单元N`

| | 旧（title 模式） | 旧（section 模式） | 新（统一） |
|---|---|---|---|
| 题目目录 | `第1题/`、`第2题/`... | — | `单元1/`、`单元2/`... |
| 知识目录 | `知识/`（独立文件夹） | — | 自然的 `单元N/` |
| 板块目录 | — | `板块1/`、`板块2/`... | `单元N/` |

统一后的讲义拆分输出：

```
output/校对结果/{文档名}/
├── 单元1/          # 引言或第一个标题前的内容
├── 单元2/          # 第一个匹配的标题块（可能是知识或题目）
├── 单元3/
└── ...
```

### 决策 3：废弃 `generate_knowledge`

section 模式下知识标题已被识别为板块边界，知识自然成为独立单元，不再需要单独的 `知识/` 文件夹。

- `default_generate_knowledge`：保留函数体（不做 breaking change），加 deprecation 日志
- `BaseSubjectApp.generate_knowledge()`：section 模式下直接 return（no-op）
- `ui/default_app.py`：section 模式下跳过 `generate_knowledge` 调用

### 决策 4：学科扩展关键词留空，后续按需追加

`config.json` 中新增 `lecture_split.section_pattern_extensions` 字段（字符串数组），默认空数组。

各学科后续可根据文档实际情况追加领域特有词，例如：
- 语文：`写作指导`、`素材积累`
- 物理：`实验探究`
- 化学：`反应原理`

**高中历史**的 `config.json` 保持原样不动（已有成熟的 section 配置，其 `section_pattern` 直接覆盖默认值）。

### 决策 5：统一手动拆分标记

当前 `core/manual_split.py` 有两套标记：
- `###### 题目开始 ######` / `###### 题目结束 ######`
- `###### 知识开始 ######` / `###### 知识结束 ######`

统一为单一标记：

```
###### 单元开始 ######
（单元内容）
###### 单元结束 ######
```

- 不再区分"题目"和"知识"——和目录命名 `单元N/` 保持一致
- `split_by_manual_markers()` 和 `split_by_knowledge_markers()` 合并为 `split_by_unit_markers()`
- 智能拆分的标记也从 `<problem>` 改为 `###### 单元开始 ######` / `###### 单元结束 ######`（见 ADR-0018）

### 决策 6：去掉 `is_knowledge` 程序分支

当前 `is_knowledge` 的判断依据是目录名是否为 `"知识"`。统一为 `单元N/` 后，`知识/` 目录不再存在，`is_knowledge` 永远为 False。

在 ReAct 模式下，`is_knowledge` 早已被架空——`get_question_prompt()` 和 `get_knowledge_prompt()` 返回相同的 `agent_prompt`，LLM 通过"第 0 步"自行判定内容类型。去掉 `is_knowledge` 不会影响校对质量。

**改动**：
- `BaseSubjectApp.proofread_one()`：移除 `is_knowledge` 参数
- `default_proofread_one()`：移除 `is_knowledge` 参数
- `ui/default_app.py`：移除 `is_knowledge = (q_name == "知识")` 逻辑
- 保留 `knowledge_prompt_lines` 字段在 config 中（向后兼容），但不再使用

### 决策 7：装饰图片清除提升到 `default_split_lecture` 内部

当前 9 个学科的 `split_lecture` 各自调用 `strip_decor_images_from_file`（7 个学科的代码完全一致）。将此逻辑提升到 `default_split_lecture` 内部，作为拆分前的统一预处理步骤。

```python
# default_split_lecture 开头新增：
from shared.decor_utils import strip_decor_images_from_file
strip_decor_images_from_file(md_file)
```

- 各学科的 `split_lecture` 不再需要单独调用
- 清除逻辑与拆分模式无关（rule/smart/manual/none 都受益）
- 高中历史/语文的复杂 `split_lecture` 可以简化

### 决策 8：两级拆分 —— 板块内例题提取

一级拆分（`##`/`###`）切出大板块后，板块内部可能包含**真正的例题**（带 `**例1**`、`**教师版**`、`**练1**` 等粗体标记的完整题目）。这些例题应从知识板块中**剥离**出来，形成独立的校对单元。

**二级提取**复用 `wrapped_patterns`（section 模式下闲置），匹配行首为 `**{pattern}**` 的例题标记：

```
一级拆分：### 模型大招  →  板块"模型大招"
                                │
二级提取：  ├── 单元N:   模型大招_知识（自由落体知识讲解，无例题）
           ├── 单元N+1: 教师版（2024·广西）
           ├── 单元N+2: 教师版（2025·湖南衡阳）
           └── 单元N+3: 例4（2021·湖北）
```

**无标记的内联题**（如化学的"判断正误：①...②..."）不触发提取，留在知识单元内与知识一起校对。

**提取规则**：
- 匹配行 + 后续内容 → 独立例题单元（直到下一个一级边界或二级例题标记）
- 非匹配内容 → 累积为知识单元
- 连续编号：知识单元和题目单元按原文出现顺序统一编为 `单元N`

### 决策 9：导航区保留但跳过校对

板块拆分后，导航/封面内容（`### 直击课堂`、`#### 本讲导航`、`考情分析` 等）形成的单元保留目录，但校对时跳过。

**机制**：`remove_navigation_units` 改为 `mark_navigation_units`——不再删除目录，而是在目录中创建 `.skip_proofread` 标记文件。

- 匹配规则：单元首行匹配 `直击课堂`、`本讲导航` 等模式
- UI 校对流程检测 `.skip_proofread` 文件，自动跳过该单元
- 目录和内容保留（考情分析等信息有参考价值）

### 决策 10：连续标题合并

当多个一级边界（`##`/`###`）连续出现、中间无实质内容时，合并为一个单元。

```
## 模块一 化学键        ← 无实质内容
### 必备知识            ← 合并到同一单元
相邻的原子（或离子）...  ← 从这里开始有实质内容
```

**实现**：遇到新边界时，检查当前累积内容是否只有标题行+空行。若是，不结束单元，而是将新标题追加到当前单元（标题取最后一个，所有标题行保留在内容中）。

**效果**：消除 `## 模块N` 紧接 `### 必备知识` 产生的空壳单元。从 13 个减少到 9 个。

---

## 影响

### 正面

- **简化拆分逻辑**：title/section 双模式收敛为单一 section 模式，减少分支
- **自然阅读顺序**：知识和题目按原文顺序排列为 `单元1、2、3...`，审核时顺序阅读即可
- **消除知识提取 bug**：不再依赖 `generate_knowledge` 的行过滤逻辑（该逻辑经常漏掉或错误归类内容）
- **下游统一**：所有学科的校对入口看到的都是 `单元N/` 结构
- **例题独立校对**：`**例1**` / `**教师版**` 等真正例题从知识板块剥离，独立校对，排版时可灵活排列
- **导航区保留**：考情分析等参考内容保留但不浪费校对 token

### 负面

- **一次性迁移成本**：8 个学科的 `config.json` 需要更新（加 `split_mode: "section"`，清空 extensions）
- **单元数量增加**：二级提取后单元数可能翻倍（每个例题独立 + 知识板块）
- **目录命名变更**：已有的 `第N题/` → `单元N/` 变化可能影响已有 session 文件

### 中性

- **高中历史零改动**：唯一已使用 section 模式的学科，仅 `板块N` → `单元N` 名称变化
- **试卷拆分不受影响**：`exam_split` 保持 `第N题` 命名，试卷无知识部分

---

## 实施计划

| 优先级 | 文件 | 改动 |
|--------|------|------|
| P0 | `core/defaults.py` | 默认 section 模式 + `DEFAULT_SECTION_PATTERN` + 二级例题提取（复用 `wrapped_patterns`）+ `单元N` 命名 + generate_knowledge deprecation + `strip_decor_images_from_file` 统一预处理 |
| P0 | `shared/split_post_utils.py` | `remove_navigation_units` → `mark_navigation_units`（创建 `.skip_proofread` 替代删除目录） |
| P0 | `core/config_loader.py` | 导出 `DEFAULT_SECTION_PATTERN`；`get_section_pattern` 合并 base + extensions；默认 mode → section |
| P0 | `core/config_schema.py` | 默认 mode → section；新增 `section_pattern_extensions` 字段 |
| P1 | `core/manual_split.py` | 统一标记为 `###### 单元开始/结束 ######`；合并题目/知识拆分为 `split_by_unit_markers()` |
| P1 | `core/base_subject.py` | `generate_knowledge` 加 deprecation 日志 + section 模式 no-op；`proofread_one` 移除 `is_knowledge` 参数；适配新的 manual split 调用 |
| P1 | `core/defaults.py` | `default_proofread_one` 移除 `is_knowledge` 参数 |
| P1 | `ui/default_app.py` | `generate_knowledge` 调用点适配 section 模式；移除 `is_knowledge` 目录名判断逻辑 |
| P1 | `ui/default_app.py` | `generate_knowledge` 调用点适配 section 模式 |
| P2 | 9 个学科 `subject.py` | 移除各自的 `strip_decor_images` 调用（已提升到 defaults.py）；更新 `split_mode` 配置 |
| P2 | 测试更新 | `test_base_subject.py`、`test_config_schema.py`、`test_subject_v2_compat.py` |
