# ADR 0016：工具生成校对标记 —— 替代 LLM 手写内联标记

**状态**：未实现（待合并）— 已落地的仅有 EditFileTool 与手动标记统一；add_proofread_mark / update_proofread_mark 仍在分支 feat/add-proofread-mark 待合并
**日期**：2026-07-07
**实现日期**：2026-07-09
**决策者**：MikeTheWiTness
**关联**：[[ADR 0005 ReAct 机制]](0005-react-mechanism-architecture.md)、[[ADR 0015 统一校对流程]](0015-unified-proofread-flow.md)

---

## 背景

当前校对流程中，LLM 在文本输出中手写内联标记格式 `【N|原文|改为】`。这带来三个问题：

1. **Token 浪费**：LLM 必须在输出中重复大量原文，同一段文字在输入和输出中各出现一次
2. **复制错误**：LLM 经常截断、改写或省略原文，导致标记中的"原文"与实际文件不符
3. **格式错误**：编号遗漏/重复、`|` 分隔符缺失、标记与原因数量不匹配，需要格式审查（二级制）兜底

**本 ADR 引入专用工具 `add_proofread_mark` / `update_proofread_mark`，让 LLM 通过工具调用生成标记，替代手写方式。校对范式不变（保留 `【N|原文|改为】` 格式），双栏报告生成不受影响。**

---

## 决策

### 决策 1：新增 `add_proofread_mark` 工具

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `paragraph` | int | 段落号（LLM 通过 `read_section` 已知） |
| `original` | str | 要标记的原文片段（短字符串，如"北京"） |
| `occurrence` | int = 1 | 该片段在段落中的第几次出现 |
| `corrected` | str | 修改后的文字 |
| `reason` | str | 修改原因 |

**行为**：
1. 读取目标文件 → 按段落拆分
2. 定位到第 `paragraph` 段
3. 找到第 `occurrence` 次出现的 `original`（**忽略已被标记替换的文字**）
4. 将 `original` **替换为** `【N|original|corrected】`（N 自动递增编号，从 1 开始）
5. 在文件末尾 `### 修改原因` 章节追加 `N. reason`

**定位原理**：`paragraph + original + occurrence` 三要素精确定位。替换模式保证已标记文字被"消费"，后续 occurrence 计数不受影响。

```
示例：
  原文：小明今天去了北京，然后从北京坐飞机去了上海。
  
  LLM 调用：
    add_proofread_mark(paragraph=1, original="北京", occurrence=2,
                       corrected="上海", reason="地点错误")
  
  文件变为：
    小明今天去了北京，然后从【1|北京|上海】坐飞机去了上海。
  
    ### 修改原因
    1. 地点错误
```

### 决策 2：新增 `update_proofread_mark` 工具

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `mark_number` | int | 要修改的标记编号 |
| `original` | str = None | 新原文（可选，不改则留空） |
| `corrected` | str = None | 新修改后文字（可选） |
| `reason` | str = None | 新修改原因（可选） |

**行为**：
1. 在文件中找到 `【N|...|...】` → 更新指定字段
2. 在 `### 修改原因` 中找到 `N. ...` → 更新原因
3. 至少提供一个要修改的字段

### 决策 3：文件操作流程变更

```
【当前】
源文件.md → call_api(全文传入) → LLM 输出全文+标记 → 写 _校对报告.md → 格式审查 → 修正

【新流程】
源文件.md → 复制到 _校对报告.md（源文件全文 + ### 修改原因 空章节）
          → call_api（传入全文 + 文件工具集）
          → LLM 逐条调用 add_proofread_mark / update_proofread_mark 编辑文件
          → _校对报告.md 即最终报告
          → 格式审查可跳过（工具保证格式正确）
```

**`_校对报告.md` 初始结构**（纯文本开头，无 `### 标记原文` 章节标题）：
```
{源文件全文}

### 修改原因

```

### 决策 4：LLM 可用的文件工具集

| 工具 | 用途 |
|------|------|
| `read_file` | 读取文件内容（增强：加 offset/limit 按行读取） |
| `add_proofread_mark` | 添加校对标记 |
| `update_proofread_mark` | 修改已有标记 |
| `edit_file` | 通用搜索替换（非标记的文本修正，如格式调整） |
| `write_file` | 全量覆盖写入（重大结构调整时兜底） |

**不暴露 BashTool**：有上述工具即可覆盖所有场景，bash 增加不必要的复杂度。

### 决策 5：文件路径注入方式

参照 `text_nav_tools.py` 的 `set_current_text()` 模式，在 `shared/bash_tool.py` 中新增：

```python
_current_file: threading.local = threading.local()

def set_current_file(path: str): ...
def get_current_file() -> str: ...
```

在 `default_proofread_one` 调用 `call_api` 前注入 `_校对报告.md` 的路径。

### 决策 6：`_校对数据.json` 生成方式

**从 `tool_calls_log` 提取**，而非从文件解析。

每次 `add_proofread_mark` / `update_proofread_mark` 调用记录在 `tool_calls_log` 中，包含完整参数（paragraph, original, corrected, reason 等）。从中提取生成结构化 JSON，比从文件反解析更可靠。

### 决策 7：与现有流程的兼容策略

**新增为可选模式，不替换现有内联标记流程**。

- `BaseSubjectApp` 新增 `_use_tool_marks` 开关（默认 False）
- 开关打开时：`build_tools()` 追加文件工具，prompt 切换到工具标记版本
- 开关关闭时：完全保留现有行为，零影响
- 先在语文学科试验，验证通过后逐步推广

### 决策 8：格式审查简化

工具生成的标记格式由代码保证，不再需要：
- `_enforce_format` 的标记编号/原因数量一致性检查
- `_llm_format_fix` 的 LLM 格式修正

但保留基础的完整性检查（文件非空、修改原因章节存在等）。

---

## 影响

### 正面

- **Token 节省**：LLM 输出从"全文+标记"变为"短参数工具调用"，输出 token 大幅下降
- **格式零错误**：编号、分隔符、原因对应由工具代码保证，消除当前最常见的格式问题
- **杜绝复制错误**：LLM 不再需要复制原文，`original` 参数仅用于定位匹配，不依赖精确复制
- **双栏报告兼容**：`_校对报告.md` 中仍有完整的 `【N|原文|改为】` 标记，下游解析和报告生成无需改动
- **修改可追溯**：`tool_calls_log` 完整记录每次标记的参数，比从文本解析更可靠

### 负面

- **增加工具调用轮次**：每个标记需要一次工具调用，多错误场景下 max_loops 可能需要上调
- **paragraph 计数敏感**：如果文件段落划分与 LLM 认知不一致，定位可能失败
- **occurrence 计数依赖 LLM 准确性**：LLM 需要正确数出目标文字是段落中第几次出现

### 中性

- **`BaseSubjectApp` 需要轻微扩展**（添加开关 + 文件工具注入），但各学科 `build_tools()` 无需修改
- **提示词需要新增工具使用指南**，描述 `add_proofread_mark` 的参数语义和定位规则

---

## 未决问题（待落地阶段解决）

1. **max_loops 阈值**：文件编辑模式每个标记消耗一轮，需评估典型场景的轮次需求
2. **update_mark 的实现复杂度**：正则匹配 `【N|...|...】` 在段落内嵌场景下的鲁棒性
3. **并发安全**：线程局部存储 + 文件写入的并发竞争（当前为单线程校对，风险低）
4. **occurrence 数错容错**：LLM 数错出现次数时，工具报错信息如何帮助 LLM 快速修正

---

## 实施计划

| 优先级 | 文件 | 改动 |
|--------|------|------|
| P0 | `shared/bash_tool.py` | 新增 `add_proofread_mark` + `update_proofread_mark` + `set_current_file`；增强 `FileReadTool` |
| P0 | `shared/bash_tool.py` | 新增 `EditFileTool`（通用搜索替换） |
| P1 | `core/defaults.py` | `default_proofread_one`：文件复制、路径注入、工具合并、JSON 生成 |
| P1 | `core/base_subject.py` | 新增 `_use_tool_marks` 开关 + `build_file_tools()` 方法 |
| P1 | `core/api_client.py` | `_NAV_CONTROL_TOOLS` 扩展 + `edit_file` / `add_proofread_mark` |
| P2 | `subjects/高中语文v3.0/agent_prompt.json` | 新增工具使用指南（定位规则 + 参数语义） |
| P2 | 测试 | `add_proofread_mark` 单元测试（多出现/替换/编号）+ 集成测试 |
