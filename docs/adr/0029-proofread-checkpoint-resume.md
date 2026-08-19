# ADR 0029：校对断点续传（磁盘快照 + 自动恢复）

**状态**：已实现（commit 7bbfa7c）
**日期**：2026-08-18
**决策者**：MikeTheWiTness
**关联**：[[ADR 0021 call_api 重构]](0021-call-api-refactor-bashtool-safety-test-degradation.md)、[[ADR 0028 工具循环搜索配额与选择性熔断]](0028-tool-loop-search-quota-and-selective-circuit-break.md)

---

## 背景

`call_api` 的重试循环每次从零重建 `messages`：网络波动触发重试时，工具循环已完成的调用历史与 LLM 中间结果全部丢失，从头再跑，重复消耗 token 和时间。程序关闭/中断后，单元内没有任何对话中间状态可恢复；`SessionManager` 仅记录任务级完成/失败状态。

## 决策

**为单单元校对引入磁盘快照断点续传：`<单元目录>/_校对续传.json`。**

### 门控：`SessionContext.enable_checkpoint`（默认 False）

call_api 共有 4 个调用方（校对主流程 / format_enforcement 格式修正 / smart_split 智能分割 / e2e 脚本），无条件检测快照会误伤后三者（格式修正与主流程共用单元目录；e2e 会非确定性续传残留快照导致测试不可复现）。因此：

- `SessionContext` 新增 `enable_checkpoint: bool = False` 字段，`call_api` 读取——与 `max_loops` 由 ctx 携带同一模式
- 仅 `default_proofread_one` 在调用前开启；格式修正 / 智能分割 / e2e 零改动，行为确定

### 快照内容

**快照 = `ProofreadState.dump()`，与工具循环状态是同一个数据结构**（见下节），杜绝「快照字段清单」与「循环状态清单」两份清单漂移。字段：

- `messages`（完整 system/user/assistant/tool 历史；图片以**文件名清单**存储，见下）
- `tool_calls_log`、`reasonings`、`assistant_turn`、`total_usage`
- `loop`、`search_count`、`empty_streak`、`recent_results`
- `openai_tools`（可能已移除搜索工具）、`reasoning_effort`
- 校验字段：`q_title`、`prompt_hash`、`md_hash`、`model`
- `initial_header`、`schema_version`

`payload` 不入快照——纯派生件（ctx + messages + openai_tools 每轮重建）。

### 快照粒度：轮次边界

一轮 assistant 消息可含多个 tool_calls；OpenAI 协议要求每个 `tool_call_id` 有对应 tool 消息，半执行轮次的快照直接续发必 400。因此：

- 保存点：整轮工具结果全部回填完毕、发下一轮请求之前（含压缩历史后）
- 快照永远是协议合法状态，恢复后可直接续发
- 崩溃在轮内 → 回退到上一完整轮次，**整轮重放**（不做按 tool_call_id 的 diff 补齐——工具只读/幂等假设下整轮重放语义简单一个量级）

### 保存与清除

- 原子写：临时文件 + `os.replace`（与 `SessionManager._save` 同模式），支持并行校对
- 清除：单元正常完成（END_TURN/MAX_TURNS/TOOL_LOOP）后删除快照
- 保留：ERROR/用户中断后保留，供下次续传

### 恢复与四重校验

`call_api` 入口（仅 `enable_checkpoint=True` 时）检测快照，**四重校验任一不匹配即不恢复**：

| 校验 | 防的场景 |
|---|---|
| `q_title` | 单元错位 |
| `prompt_hash`（system_prompt 哈希） | 批注评审与普通校对共用 q_dir/q_title（prompt 不同）；学科 prompt 迭代后的旧语义快照 |
| `md_hash`（**pre_hook 之前**的原始单元 md 哈希） | 用户编辑题目后重跑。必须在 `read_md_for_unit` 之后、pre_hook 之前计算——高中语文 pre_hook 每次重跑动态注入「前置参考」，hook 后文本不能作校验基准 |
| `model` | 换模型后续传（纯文本模型回放含图消息必 400；换模型本身也应重开对话） |

**校验失败分两类处理**：

- **文件级损坏**（JSON 解析失败 / `schema_version` 不认识 / 缺必需字段）：重命名为 `_校对续传.corrupt.json` 保留——损坏是异常，留排查现场
- **校验不匹配**（四重校验任一失败）：直接删除快照——换模式/改题/换模型是正常操作流转，无痕进行。不留 `.mismatch` 文件（会随每次正常变更堆积孤儿文件）

### 图片：路径引用 + 恢复时重编码

快照不存 base64（多图单元快照可达几十 MB × 每轮全量重写 × 并行单元数，IO 放大发生在功能主场景）。快照存图片文件名清单，恢复时从 `q_dir/images/` 重新编码回填（复用 `default_proofread_one` 现有编码逻辑：mime 判断 + 10MB 过滤）。图片文件缺失时 log 警告、该图降级缺失。纯文本模型剥图语义无需恢复路径处理——`model` 校验已保证恢复时模型与快照时相同。

### 恢复可见性：log 单行提示，零交互

不弹窗（并行多单元命中快照会连环弹窗阻塞 worker）；也不完全静默（用户排查 token 用量跳变需要线索）。恢复时 log 单行：`⏩ 第X题：检测到中断快照（已进行 N 轮工具循环），从断点续跑`。

### `ProofreadState` 状态机

`_run_tool_loop` 的全部循环状态（messages + `loop`/`recent_results`/`empty_streak`/`search_count`/`reasonings`/`assistant_turn` + 突变后的 `openai_tools`）收拢为 `ProofreadState`，快照即 `state.dump()` / `state.load()`。`_run_tool_loop` 签名从 11 参数收敛为 `(ctx, state, tool_instances, chat_url, headers)`；现有 8 个契约测试（`tests/test_api_client.py::TestRunToolLoopRobustness`）断言对象全在 state 上，移植是机械的。这是 ADR-0021 / CONTEXT.md 2.1（State vs Config 分离，参考 Claude Code `queryLoop`）既定方向的完成，非新增决策。

### 重试语义

`_run_tool_loop` 基于 `ProofreadState` 续跑；重试时携带已有 `messages` 继续，不重放已完成的工具。仅首次请求失败（无历史）才从零开始。

## 取舍

- **自动恢复 vs 弹窗确认**：选自动恢复（零交互，log 单行提示；删除快照文件即可强制重来）
- **完整 messages vs 摘要压缩**：选完整保存（图片除外——路径引用），实现简单、恢复准确
- **轮次边界 vs 工具边界快照**：选轮次边界。工具边界省的 token 抵不上「按 tool_call_id diff 补齐」的 bug 面；断点续传的价值在长循环的大数，不在最后一轮零头
- **ProofreadState 全量收拢 vs 仅快照 DTO**：选全量收拢。仅 DTO 会造成两份清单手工同步，忘一次即静默丢失续传数据
- **工具重放风险**：崩溃在轮内则整轮重放该轮工具；项目工具为只读或幂等写入，风险可接受

## 实施顺序（issue 拆分基础）

1. **ProofreadState 预重构**：收拢循环状态 + 移植 8 个契约测试（纯重构，零行为变更）
2. **快照保存/原子写**：轮次边界保存点 + dump
3. **恢复 + 四重校验**：load + 校验 + 损坏/不匹配分流 + log 提示
4. **重试语义改造**：重试携带已有 messages
