# 044 — TOOL_LOOP 触发时只移除搜索工具 + 搜索独立配额

## 背景

当前 `core/api_client.py` 中，当 `empty_streak >= 3`（连续 3 轮空/重复结果）触发 `TOOL_LOOP` 分支时，执行：

```python
openai_tools = None
payload["tools"] = None
```

即**将所有工具全部移除**。但这不合理——`web_search` 搜不到结果不代表其他工具（`read_file`、`write_file`、`locate_paragraph` 等）也不能用。

此外，搜索（`web_search` / `web_fetch`）不应占用主循环轮次配额（`loop`），否则搜索多了就吃光 MAX_TURNS。

## 改动

### 1. 搜索独立配额（5 次）

- `web_search` / `web_fetch` 单独计数 `search_count`，上限 5 次
- 纯搜索轮次（全部 tool_call 都是搜索）**不增加 `loop`**，不消耗 MAX_TURNS
- 混合轮次（搜索 + 其他工具）正常增加 `loop`
- 搜索配额耗尽后：只移除搜索工具，保留其他工具，注入提示

### 2. 搜索工具排除出 empty_streak

- 搜索工具不再计入 `empty_streak`（有自己的配额机制）
- TOOL_LOOP 仍保留作为其他工具的兜底

### 3. TOOL_LOOP 分支只移除搜索工具

- `openai_tools = None` → 过滤掉 `web_search` / `web_fetch`，保留其他
- `_compress_history` 新增 `disable_all` 参数，TOOL_LOOP 场景提示"搜索已禁用但其他工具仍可用"

### 4. MAX_TURNS 分支不变

- MAX_TURNS 语义为轮次耗尽，保持全部去工具行为

## 验收标准

- [x] 纯搜索轮次不占 `loop`
- [x] 搜索配额 5 次耗尽后，搜索工具被移除，其他工具仍可用
- [x] 搜索工具不触发 empty_streak → TOOL_LOOP
- [x] TOOL_LOOP 触发后只移除搜索工具
- [x] 提示语区分"全部禁用"(MAX_TURNS) 和 "仅搜索禁用"(TOOL_LOOP)
- [x] 现有测试全部通过（580 passed）
