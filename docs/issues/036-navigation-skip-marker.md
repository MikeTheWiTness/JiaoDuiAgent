# Issue 036：导航区 `.skip` 标记

**关联 ADR**：[ADR-0017](../adr/0017-unified-section-split.md)（决策9）

---

## What to build

当前 `remove_navigation_units` 直接删除导航/封面板块目录。改为保留目录但标记为"跳过校对"。

### 1. `mark_navigation_units` 替代 `remove_navigation_units`

- 不再 `shutil.rmtree` 删除目录
- 在匹配的单元目录中创建 `.skip_proofread` 标记文件
- 匹配规则：单元首行匹配 `直击课堂`、`本讲导航` 等模式（保持 `DEFAULT_NAV_PATTERNS`）

### 2. UI 校对流程跳过

- `ui/default_app.py` 在遍历单元进行校对时，检测 `.skip_proofread` 文件
- 存在则跳过该单元，输出日志 `⏭️ 单元N 标记为跳过校对`

### 3. 更新调用方

- 高中历史 `split_lecture` 中 `remove_navigation_units` → `mark_navigation_units`
- 其他学科按需接入（导航区普遍存在）

## Acceptance criteria

- [ ] 导航单元目录保留（不删除），含 `.skip_proofread` 文件
- [ ] UI 校对流程自动跳过带 `.skip_proofread` 的单元
- [ ] 日志输出跳过信息
- [ ] 普通单元（无 `.skip_proofread`）正常校对
- [ ] 单元测试覆盖：标记创建、UI 跳过逻辑

## Blocked by

- Issue 033（`parse_unit_markers` 共用解析器可辅助定位首行）
