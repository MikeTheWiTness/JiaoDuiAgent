# Issue 043：断链修复 + 决策 9 接线 —— 单元N 识别 / manual 标记 / 导航跳过

**关联 ADR**：[ADR-0019](../adr/0019-architecture-review-fixes.md)（决策 14/15）、[ADR-0017](../adr/0017-unified-section-split.md)（决策 5/9）

---

## What to build

三个因 ADR-0017/0018 落地一半产生的断链一次修通：「选择根目录」批量入口认不出新拆分产物、manual 拆分不认新标记、`.skip_proofread` 协议写读两侧断链。

### 1. 🔴4 单元N 识别

- `core/defaults.py` 的 `_is_unit_dir`：补「单元」前缀识别（当前只认「题」/「板块」）
- 效果：ADR-0017 之后的 `单元N/` 拆分产物可被「选择根目录」批量入口正确识别
- **回归锁**：`_is_unit_dir` 识别测试（单元N / 第N题 / 板块N / 混合目录）

### 2. 🔴7 manual 拆分标记切换

- manual 模式入口（`core/base_subject.py` 的 `split_exam`、高中语文/高中历史 `split_lecture`）从 `split_by_manual_markers`（旧 `###### 题目开始 ######`）切到 `split_by_unit_markers`（新 `###### 单元开始/结束 ######`，ADR-0018 已统一）
- 效果：用户按新约定写标记选 manual 不再报「未找到任何题目标记」

### 3. 🔴6 初中英语 NameError

- `subjects/初中英语v3.0/subject.py` 的 `get_tool_instructions`：未定义变量 `tools` 改为 `self.tools`（ReAct 模式必崩）
- 顺带核对小学语文/初中英语的 `PlanUpdateTool(nudge_template="")` 与其他 5 科一致性

### 4. 决策 9 接线：导航区标记替代删除

- 高中历史 `subject.py`：`remove_navigation_units`（真删目录）→ `mark_navigation_units`（创建 `.skip_proofread`）
- 评估 `default_split_lecture` 是否统一调用（决策原意是所有学科受益）
- 效果：考情分析等导航内容保留目录但校对自动跳过；Issue 039 的契约测试从「协议空转」变为「真实生效」

## Acceptance criteria

- [ ] 「选择根目录」能识别含 `单元N/` 的拆分产物目录
- [ ] `_is_unit_dir` 回归锁测试通过
- [ ] manual 拆分接受 `###### 单元开始/结束 ######` 标记并成功拆分
- [ ] 初中英语 ReAct 模式 `get_tool_instructions` 不再 NameError
- [ ] 高中历史拆分后导航单元含 `.skip_proofread` 标记、目录保留、校对自动跳过
- [ ] `pytest` 保持全绿

## Blocked by

- Issue 042（同学科 subject.py 的删除改动先行，避免冲突）
