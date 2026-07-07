# Issue 038：智能拆分工具化 + 标记统一

**关联 ADR**：[ADR-0018](../adr/0018-smart-split-tool-integration.md)

---

## What to build

智能拆分从"LLM 输出全文+标签"改为"LLM 用工具在文件中插入标记"，并统一标记格式。

### 1. 标记统一

智能拆分不再使用 `<problem>...</problem>`，改为和手动拆分一致的：

```
###### 单元开始 ######
（单元内容）
###### 单元结束 ######
```

共用 Issue 033 的 `parse_unit_markers()` 解析器。

### 2. 文件工作流

```
源文件 → _split_working.md → LLM 用 read_file 读取
                            → LLM 用 edit_file 插入 ###### 标记
                            → parse_unit_markers() 提取单元
                            → 清理临时文件
```

### 3. `smart_split` 重写

- 不再通过 `call_api` 传入全文
- 改为：写入临时文件 → `call_api`（带 `read_file` + `edit_file` 工具）→ 解析
- 保留 `smart_split_with_callable` 接口兼容
- 中间产物从 `_smart_split_raw.md` 改为 `_split_working.md`

### 4. Prompt 更新

`SMART_SPLIT_PROMPT` 从"输出全文+标签"改为：
```
1. 用 read_file 读取文件
2. 识别每个单元的起始和结束位置
3. 用 edit_file 在起始前插入 ###### 单元开始 ######
4. 用 edit_file 在结束后插入 ###### 单元结束 ######
5. 完成后用 read_file 验证标记完整性
```

## Acceptance criteria

- [ ] 智能拆分输出结果与手动拆分使用同一套解析器
- [ ] LLM 不再输出全文（仅工具调用）
- [ ] 临时文件 `_split_working.md` 成功则删除、失败则保留
- [ ] `parse_unit_markers()` 解析 `######` 标记正确
- [ ] 和原有 `<problem>` 标签的拆分结果对比验证
- [ ] 集成测试：真实文档 → 智能拆分 → 单元数/内容验证

## Blocked by

- Issue 033（`edit_file` 工具 + `parse_unit_markers` 解析器）
- Issue 034（规则拆分 section 模式上线后，智能拆分的结果格式与规则拆分一致）
