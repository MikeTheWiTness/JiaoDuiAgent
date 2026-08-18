# Issue 050：快照保存 —— 轮次边界 + 原子写 + 生命周期

**关联 ADR**：[ADR-0029](../adr/0029-proofread-checkpoint-resume.md)（快照内容 / 快照粒度 / 保存与清除 / 门控 / 图片各节）

---

## What to build

单元校对运行中，在协议合法的轮次边界把对话状态落盘为 `<单元目录>/_校对续传.json`；单元正常完成即清除，中断/出错则保留供下次续传。本 issue 只做**保存**，恢复（检测、校验、续跑）归 Issue 051。

### 门控：默认关，仅校对主流程开

- `SessionContext` 新增 `enable_checkpoint` 布尔字段，默认 `False`，`call_api` 读取——与 `max_loops` 由 ctx 携带同一模式
- 仅校对主流程入口（`core/defaults.py` 的默认校对实现）在调用前开启
- 其余 3 个 `call_api` 调用方（格式修正 / 智能分割 / e2e 脚本）零改动、行为确定（不检测、不落盘）

### 保存点：轮次边界

- 每轮工具结果**全部回填完毕**、发下一轮请求之前保存；压缩历史后同样保存
- 快照永远处于「完整历史 + 等待下一次 LLM 响应」的协议合法状态（每个 tool_call_id 均有对应 tool 消息）
- 不做单工具边界保存（半执行轮次续发必 400，diff 补齐的复杂度被 ADR-0029 否决）

### 快照内容 = `ProofreadState.dump()`

- 快照与循环状态是同一个数据结构，序列化即保存；后续新增循环状态字段自动进快照，杜绝两份清单漂移
- 校验字段本 issue 一并写入：`q_title`、`prompt_hash`、`md_hash`（**pre_hook 之前**的原始单元 md 哈希——高中语文 pre_hook 每次动态注入前置参考，hook 后文本不能作基准；计算点在单元 md 读取之后、前置 hook 之前）、`model`
- `schema_version` 前置
- **图片存文件名清单，不存 base64**（多图单元每轮全量重写几十 MB 不可接受）；恢复时重编码归 Issue 051

### 生命周期

- 原子写：临时文件 + `os.replace`（与 SessionManager 同模式），支持并行校对（每单元独立目录天然隔离）
- 清除：END_TURN / MAX_TURNS / TOOL_LOOP 正常完成后删除
- 保留：ERROR / 用户中断后保留
- 本 issue 落地后，删除快照文件 = 强制从零开始的用户逃生口

### 文档同步

- AGENTS.md「中间产物的保存路径」清单收录 `_校对续传.json`（含命名约束：禁用自由命名副本文件）

## Acceptance criteria

- [ ] `enable_checkpoint` 默认 False；格式修正 / 智能分割 / e2e 调用路径无任何快照文件产生
- [ ] 工具循环中断（用户中断或 ERROR）后，单元目录存在 `_校对续传.json`，且 messages 为协议合法状态（无悬空 tool_call_id）
- [ ] 单元正常完成（三种 stop_reason）后，快照文件已删除
- [ ] 快照含校验四字段（q_title / prompt_hash / md_hash / model）与 schema_version
- [ ] 快照中图片以文件名清单形式存在，无 base64 数据
- [ ] md 哈希取自 pre_hook 之前的原始单元文本（语文前置参考注入不改变哈希值）
- [ ] 并行校对多单元，各单元快照互不干扰（原子写无交错损坏）
- [ ] AGENTS.md 中间产物清单已收录快照文件名
- [ ] 全量 `pytest` 保持全绿

## Blocked by

- Issue 049（ProofreadState——快照 dump 以 state 为载体）
