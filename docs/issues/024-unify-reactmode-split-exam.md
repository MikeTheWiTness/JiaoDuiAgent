# Issue 024：`react_mode` 统一为 property + `split_exam` 模板化

## Parent

ADR-0011（学科代码重复消除与共享层提取）— react_mode 不一致 + split_exam 重复

## What to build

1. 将 `react_mode` 从两种实现模式统一为 property+setter 模式
2. 将 `split_exam` 模板化（`split_lecture` 暂不模板化，等待讲义块拆分设计稳定）

**当前状态**：

**react_mode**：
- 5 科用普通属性：`self.react_mode = False`（切换时不重建 tools）
- 2 科（语文、历史）用 property+setter：`self._react_mode` + setter 中调用 `self.tools = self.build_tools()`

**split_exam**：
- 基本流程一致（rule → default，manual/smart/none → _write）
- 差异仅在支持的 split_mode 子集不同

**修复方向**：
1. 基类 `__init__` 统一为 property 模式：`self._react_mode = False`，setter 自动调用 `self.build_tools()`
2. 基类实现 `split_exam`：rule → default，其他模式 → 读取文件 → 调用 `_get_extra_exam_split_modes()` → 分发 → `_write_problems_to_dirs`
3. 子类覆盖 `_get_extra_exam_split_modes()` 返回额外支持的 split_mode 列表
4. **暂不处理 `split_lecture`** — 讲义拆分正在向历史模式收敛但设计未稳定

## Acceptance criteria

- [ ] 所有 7 科统一使用 property+setter 模式管理 `react_mode`
- [ ] `react_mode` 切换时自动重建 `self.tools`，行为与语文/历史现有实现一致
- [ ] 基类实现 `split_exam`，各学科只需覆盖 `_get_extra_exam_split_modes()`
- [ ] `split_lecture` 保持各学科独立实现（本期不改）
- [ ] 所有 7 个学科的工具切换和试卷拆分流程端到端通过

## Blocked by

Issue 020（基类框架存在即可，与 Issue 021-023 可并行）
