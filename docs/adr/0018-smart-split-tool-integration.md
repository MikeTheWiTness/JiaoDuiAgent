# ADR 0018：智能拆分工具化 + 标记统一 —— 用 edit_file 插入 ###### 单元标记

**状态**：已实现（commit 6ddd08b）
**日期**：2026-07-07
**实现日期**：2026-07-09
**决策者**：MikeTheWiTness
**关联**：[[ADR 0016 工具生成校对标记]](0016-tool-generated-proofread-marks.md)、[[ADR 0017 统一规则拆分]](0017-unified-section-split.md)

---

## 背景

当前 `smart_split`（`shared/smart_split.py`）的流程：

```
LLM 接收全文 + SMART_SPLIT_PROMPT
       ↓
LLM 输出全文 + <problem>...</problem> 标签
       ↓
Python 用正则提取标签内容
```

和校对标记面临相同的问题：
1. **Token 浪费**：LLM 输出中重复整个原文
2. **原文篡改**：prompt 写死"绝对不修改原文任何一个字"，但 LLM 经常违反
3. **标签格式错误**：标签忘记闭合、嵌套错误

同时，手动拆分的标记（`###### 题目开始 ######`）和智能拆分的标记（`<problem>`）**格式不统一**，各有各的解析逻辑。

---

## 决策

### 决策 1：统一拆分标记格式

手动拆分和智能拆分使用**同一套标记**：

```
###### 单元开始 ######
（单元内容）
###### 单元结束 ######
```

| | 旧标记 | 新标记 |
|---|---|---|
| 手动拆分（题目） | `###### 题目开始/结束 ######` | `###### 单元开始/结束 ######` |
| 手动拆分（知识） | `###### 知识开始/结束 ######` | `###### 单元开始/结束 ######` |
| 智能拆分 | `<problem>...</problem>` | `###### 单元开始/结束 ######` |

**理由**：
- `######` 六个井号在正常文档中几乎不可能出现，不会误匹配
- 人类可读写（手动拆分场景），LLM 也容易插入（智能拆分场景）
- 统一格式后 `manual_split.py` 和 `smart_split.py` 可共用同一套解析逻辑

### 决策 2：用 `edit_file` 工具替代 LLM 全文输出

复用 ADR-0016 中新增的 `edit_file` 工具。LLM 直接在文件中**插入**标记，而非在文本输出中**包裹**标记。

**新流程**：

```
源文件内容 → 写入临时文件 _split_working.md
                  ↓
LLM 用 read_file 读取文件，识别单元边界
                  ↓
LLM 用 edit_file 在边界处插入标记：
  edit_file(path, old_string="**例1** 题目...",
            new_string="###### 单元开始 ######\n**例1** 题目...")
  edit_file(path, old_string="...解析结束。",
            new_string="...解析结束。\n###### 单元结束 ######")
                  ↓
Python 读取 _split_working.md，用统一解析器提取单元
                  ↓
清理临时文件
```

**关键变化**：
- `smart_split()` 不再通过 `call_api` 传入全文
- LLM 的输出从"全文+标签"变为"工具调用序列"
- 原文不会被 LLM 篡改——LLM 只插入标记，不重写原文

### 决策 3：统一解析逻辑

`manual_split.py` 和 `smart_split.py` 共用同一套标记解析：

```python
# 共用常量
UNIT_START_MARKER = r"(\\?#){6}\s*单元开始\s*(\\?#){6}"
UNIT_END_MARKER = r"(\\?#){6}\s*单元结束\s*(\\?#){6}"

def parse_unit_markers(text: str) -> list[dict]:
    """解析 ###### 单元开始/结束 ###### 标记，返回单元列表。"""
```

- `smart_split.py` 的 `parse_problem_tags()` 改为调用 `parse_unit_markers()`
- `manual_split.py` 的 `split_by_manual_markers()` / `split_by_knowledge_markers()` 合并为 `split_by_unit_markers()`

### 决策 4：复用 ADR-0016 的工具

| 工具 | 来源 | 用途 |
|------|------|------|
| `read_file` | 已有 | LLM 读取文件 |
| `edit_file` | ADR-0016 新增 | LLM 插入 `######` 标记 |

### 决策 5：split prompt 适配

`SMART_SPLIT_PROMPT` 更新为工具模式：

```
旧：用 <problem></problem> 标签标记每个完整的题目单元。输出完整的带标签文本。
新：
  1. 用 read_file 读取文件
  2. 识别每个单元的起始和结束位置
  3. 用 edit_file 在起始位置前插入 ###### 单元开始 ######
  4. 用 edit_file 在结束位置后插入 ###### 单元结束 ######
  5. 完成后用 read_file 验证标记完整性
```

---

## 影响

### 正面

- **标记统一**：手动和智能拆分共用一套标记 + 一套解析逻辑
- **Token 大幅节省**：LLM 输出从全文变为短参数工具调用
- **杜绝原文篡改**：LLM 不再重写全文，只插入标记
- **人类友好**：`######` 标记比 `<problem>` 更直观，手动编辑时不易出错

### 负面

- **增加工具调用轮次**：每个单元边界需要 2 次 `edit_file`，多单元文档可能达到 10+ 次
- **文件 I/O 开销**：每次 `edit_file` 需要读+写文件

### 中性

- **解析逻辑重写**：`parse_problem_tags` 改为 `parse_unit_markers`，但逻辑更简单

---

## 依赖关系

```
ADR-0016（edit_file 工具）──→ ADR-0018（智能拆分工具化）
ADR-0017（单元命名 + manual 标记统一）──→ ADR-0018（共用标记格式）
```

ADR-0018 依赖 ADR-0016 的 `edit_file` 工具和 ADR-0017 的命名统一。

---

## 实施计划

| 优先级 | 文件 | 改动 |
|--------|------|------|
| P0 | `core/manual_split.py` | 统一标记为 `###### 单元开始/结束 ######`；合并为 `split_by_unit_markers()`；提取共用 `parse_unit_markers()` |
| P0 | `shared/smart_split.py` | 重写 `smart_split()`：文件写入 → call_api（带工具）→ `parse_unit_markers()`；更新 prompt |
| P1 | `core/base_subject.py` | manual 模式调用改为 `split_by_unit_markers()` |
| P2 | 测试 | `test_smart_split.py`：适配新标记 + 新增工具模式测试；`test_split_modes.py`：适配 manual 标记变更 |
