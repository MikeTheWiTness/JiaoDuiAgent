# Issue 037：校对标记工具 —— `add_proofread_mark` + `update_proofread_mark`

**关联 ADR**：[ADR-0016](../adr/0016-tool-generated-proofread-marks.md)

---

## What to build

新增两个专用工具，让 LLM 通过工具调用生成内联标记 `【N|原文|改为】`，替代手写方式。

### 1. `add_proofread_mark` 工具

| 参数 | 类型 | 说明 |
|------|------|------|
| `paragraph` | int | 段落号（LLM 通过 `read_section` 已知） |
| `original` | str | 要标记的原文片段（短字符串） |
| `occurrence` | int = 1 | 该片段在段落中的第几次出现 |
| `corrected` | str | 修改后的文字 |
| `reason` | str | 修改原因 |

行为：
- 读取目标文件 → 按段落拆分 → 定位 → 替换为 `【N|原文|改为】`（N 自动递增）
- 在文件末尾 `### 修改原因` 章节追加 `N. reason`
- 替换模式保证已标记文字被"消费"，后续 occurrence 不受影响

### 2. `update_proofread_mark` 工具

| 参数 | 类型 | 说明 |
|------|------|------|
| `mark_number` | int | 要修改的标记编号 |
| `original` | str = None | 新原文（可选） |
| `corrected` | str = None | 新修改后文字（可选） |
| `reason` | str = None | 新修改原因（可选） |

行为：
- 找到 `【N|...|...】` → 更新指定字段
- 在 `### 修改原因` 中找到 `N. ...` → 更新

### 3. 文件路径注入

参照 `text_nav_tools.py` 的 `set_current_text()` 模式：
- `set_current_file(path)` / `get_current_file()` — 线程局部存储
- 在 `default_proofread_one` 调用前注入 `_校对报告.md` 路径

### 4. `_校对数据.json` 生成

- 从 `tool_calls_log` 中提取 `add_proofread_mark` / `update_proofread_mark` 的参数
- 生成结构化 JSON，替代从文件反解析

## Acceptance criteria

- [ ] `add_proofread_mark` 定位替换正确（含多出现场景）
- [ ] 编号自动递增，无重复/遗漏
- [ ] `### 修改原因` 章节正确追加
- [ ] `update_proofread_mark` 修改已有标记正确
- [ ] 线程安全的文件路径注入
- [ ] `_校对数据.json` 从 tool_calls_log 正确生成
- [ ] 单元测试覆盖：单出现、多出现、替换后重新计数、update、边界错误

## Blocked by

- Issue 033（`EditFileTool` 可被本工具内部复用）
