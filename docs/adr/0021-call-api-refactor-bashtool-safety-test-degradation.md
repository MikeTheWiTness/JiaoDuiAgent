# ADR 0021：call_api 重构拆分 + 退化测试修复 + 散落超时常量上提

**状态**：已接受（待落地）
**日期**：2026-07-23（2026-07-24 修订：C4 BashTool 安全收敛剥离到独立安全议题；C5 `generate_clean_md` 加 repl 参数保留学科差异；C2 加对外 dict 字段面冻结）
**决策者**：MikeTheWiTness
**关联**：[[ADR 0019 架构审查修复]](0019-architecture-review-fixes.md)、[[ADR 0012 框架工程债]](0012-framework-engineering-debt.md)、[[ADR 0006 物理 ReAct 学科化]](0006-physics-react-subject-specialization.md)

## 范围原则

本 ADR 范围经 2026-07-24 审查，**收紧为纯优化、零功能变更**。BashTool 的安全加固（路径白名单 + 命令黑名单 + 绕过手法测试）会改变 LLM 实际可发出的命令集合，属功能行为变更——从本 ADR 剥离，单独立安全议题另起 grill。本 ADR 内 BashTool 仅保留**纯零风险项**：`timeout=30` 上提为模块级常量 `BASH_TIMEOUT = 30`（数值与现状一致）。

---

## 背景

2026-07-23 全面架构审查（4 个并行侦察代理）发现两类尚未被既有 ADR 覆盖的问题：

1. **`call_api` 单函数过载**（`core/api_client.py:417-791`，375 行）：构造 payload + 发起请求 + 工具循环（含中断/max_loops/搜索配额/空结果熔断）+ 重试熔断 + 三段错误报告，全在一个函数里。while 循环内 5 处 `return`、3 段重复的 `requests.post → raise_for_status → _accumulate_usage → resp.json()["choices"][0]` 样板（482-485、514-517、586-589、612-615）。结果是工具循环的 4 条退出路径（interrupted / max_turns / tool_loop / end_turn）零单测覆盖。`_save_conversation_log` 与 `_save_conversation_log_full`（313-361 vs 364-414）50 行逐行复制，且后者 `except: pass` 显式违反 AGENTS.md「异常必须记录完整上下文」。

2. **BashTool 命令注入风险**（`shared/bash_tool.py:41-66`）：`shell=True` 执行任意 command 字符串，`allowed_dir` 仅限制 `cwd`，不限制 LLM 通过 `cd /` 越界访问/修改 `allowed_dir` 外文件。这是给 LLM 调用的工具，安全边界必须严格。但 BashTool 是 `format_enforcement._bash_format_fix` 工具集的一部分，与 read_file/write_file 并列共存。

3. **退化测试**（`tests/test_clean_md_pipeline.py:9-15`）：`make_clean_md` 调用了真实 `strip_format_markers`，但又手写了 `批注`/`**`/`__` 三段 regex——同一组 regex 在 `core/base_subject.py:215-225` 生产代码里也手写了一份。两侧任一改了另一侧不感知，违反 AGENTS.md「禁止为通过而削弱测试」。ADR-0019 C6.5 已点名修复 `test_default_proofread_one` / `test_chemistry_balance` 两个仿冒测试，本 ADR 不与其重复——这两个文件落地后已确认 import 真实实现。

## 决策

### C1：call_api 重构为中等粒度的编排主函数 + 4 个抽取函数

**拆分粒度**：中等粒度，主函数仅编排，循环/重试/报告/post 样板各一个函数；不过度细分成"每分支一函数"，避免函数数量翻倍。

**抽取函数清单**：

1. **`_post_chat(chat_url, payload, headers) -> tuple[dict, dict]`**（薄函数）：仅"发一次请求、抓 choice + usage"，不关心"为什么要重发"。封装现在出现 4 次的 `requests.post(...) + raise_for_status() + _accumulate_usage + resp.json()["choices"][0]` 样板。压缩后的二次请求也复用 `_post_chat`——循环体内的两次二次请求（max_loops、空结果熔断）保留在 `_run_tool_loop` 内做压缩决策，但发请求动作委托给 `_post_chat`。

2. **`_run_tool_loop(ctx, choice, messages, tool_instances, openai_tools, ...) -> LoopResult`**：容纳 while 工具循环的全部状态机。引入轻量结果类型 `LoopResult`（见下）。4 条退出路径都通过返回 `LoopResult` 收口，循环体内不再用 `return` 提前退出。

3. **`_handle_retry(ctx, exc, retry, consecutive_errors, last_error_type, ...) -> tuple[bool, str, int, str]`**：重试 + 熔断的决策逻辑（错误分类、计数、退避、是否继续）。返回 `(是否继续, err_msg, 新计数, 新错误类型)`。

4. **`_build_error_report(ctx, proof_err, err_msg, q_title, consecutive_errors, last_error_type) -> str`**：构造三段 Markdown 错误摘要（不可重试 / 熔断 / 重试耗尽现在散布在 673-775）。

**主函数 `call_api` 的职责**：构造 payload + 初始 header → 调 `_post_chat` 拿首轮 choice → 调 `_run_tool_loop` 拿 `LoopResult` → 根据 stop_reason 统一落盘（调 `_save_conversation_log` 或 `_full`）→ 返回最终 dict。重试循环编排：捕获异常 → 调 `_handle_retry` 决策 → 继续/熔断/耗尽后调 `_build_error_report` 出报告。

### C2：`LoopResult` 轻量结果类型（与既有 `StopReason` 呼应）

引入 `LoopResult`（dataclass 或 typed dict）携带 `content / reasoning / messages / stop_reason / tool_calls_log / usage`。`stop_reason` 复用 `StopReason` 类的常量（`interrupted` 会在 `LoopResult` 中新增对应常量）。让"循环退出原因"从"在 return dict 里写值的隐式信号"升级为"显式状态机字段"，便于循环逻辑单测——传入 mock choice 序列即可断言不同条件触发不同 `stop_reason`。

**对外 dict 字段面冻结（严格）**：`call_api` 对外返回的 dict 必须保持现状**6 个 key**（`content` / `tool_calls_log` / `reasoning` / `messages` / `stop_reason` / `usage`）逐字不变；`call_api_continue` 现状 2 个 key（`content` / `reasoning`）不变。key 集合、顺序、值类型不可添加、不可删除、不可改类型。`LoopResult` 是内部类型——main 内 `result.as_dict()` 或 `dataclasses.asdict(result)` 转出 dict 时，对应 key 与现状严格对齐。**调用方（defaults.py / format_enforcement / smart_split）任何对 key 的读取不得被子改动影响。**

### C3：合并 `_save_conversation_log` 与 `_save_conversation_log_full`

合并为 `_save_conversation_log(messages, output_dir, initial_header, suffix="")`。文件名由 `suffix` 决定（`""` → `_API对话记录.md`，`"_full"` → `_API对话记录_full.md`）。两份签名原有的 `q_title` 参数实际未被函数体引用（initial_header 已含 q_title），从合并签名中删除。**统一错误处理策略**：两份当前的 `except` 行为不一致（`_save` 模板写 log、`_full` 用 `except: pass`），合并后必须都走 `log(完整 traceback)`——这同时完成 ADR-0019 C1.3 在 `api_client` 这一处剩余的扫尾。

### C4：BashTool 仅提超时常量（安全加固剥离）

`shared/bash_tool.py:50` `timeout=30` 硬编码上提为模块级常量 `BASH_TIMEOUT = 30`（**数值与现状完全一致**）。`_run` 体内 `timeout=30` 改为 `timeout=BASH_TIMEOUT`。

**BashTool 安全加固（路径白名单 + 命令黑名单 + 绕过手法测试）从本 ADR 剥离**——审查发现这套方案会改变 LLM 在格式修正场景下实际可发出的命令集合（保守策略下"无法解析即拒绝"会误拒合理命令），属于有意的安全加固功能变更，而非纯优化。违反本 ADR"零功能变更"原则。BashTool 安全议题单独立 ADR 另起 grill；本 ADR 不再涉及。

### C5：`test_clean_md_pipeline.py` 改为 import 真实生产实现，抽 `generate_clean_md(md_text, repl)` 公共函数保留学科差异

**关键事实（2026-07-24 审查发现）**：`core/base_subject.py:32` 的 `_clean_bold_replacement: str = "\x01"` 是**按学科可配置的类属性**——默认 6 学科用 `"\x01"`（删除粗体文本），高中历史 override 为 `"\1"`（保留粗体文本）。`base_subject.py:218` `repl = self._clean_bold_replacement`、219 `clean = re.sub(r'\*\*([^*]+)\*\*', repl, clean)` 调用点用学科自身类属性。`test_clean_md_pipeline.py:13` 的 `make_clean_md` 写死 `r'\1'`——只覆盖历史行为，对其它 6 学科是退化的。

**抽取方案**：抽 `shared/docx_format_enhancer.generate_clean_md(md_text: str, repl: str) -> str` 公共函数（接收 repl 参数）。函数体与 `base_subject.py:214-221` 现状逐字一致：

```
def generate_clean_md(md_text, repl):
    clean = strip_format_markers(md_text)
    clean = re.sub(r'<批注\s+id=\d+>.*?</批注>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'\*\*([^*]+)\*\*', repl, clean)
    clean = re.sub(r'__([^_]+)__', repl, clean)
    return clean
```

`base_subject.py:214-221` 改调 `generate_cleanMd(new_content, self._clean_bold_replacement)`——7 学科各自行为完全不变（每个学科自行传入它自己的 `_clean_bold_replacement`）。

**test 改造**：
- 删 `make_clean_md` 本地实现。
- import 真实 `generate_clean_md`。
- **必须新增两套断言**：`repl="\x01"`（覆盖默认 6 学科行为）与 `repl=r"\1"`（覆盖高中历史行为）。测试范围从 1 学科延伸到 7 学科。
- 现有 `must_preserve`/`not in` 断言全部保留——但必须两条 repl 各跑一遍（或参数化 fixture）。

这是"抽公共函数改生产结构"而非"只改测试"——抽函数后两侧都引用同一源，保留学科可配置差异（通过参数传递），单一真源、单一回归点。

---

## 明确不做（本轮范围外）

- **ADR-0019 C1.3 的剩余 6 处 except 扫尾**：除 `_save_conversation_log_full`（C3 本 ADR 合并时一并处理）外，`parsing.py:save_proofread_json`、`base_subject.py:_clean.md`、`chemistry_tools`、`chinese_classics_tools`、`defaults.py`（清洗/出题意图）的 except 补完**回归 ADR-0019 C1.3**（本 ADR 不接手，因为这是 ADR-0019 既定决策的未完成部分，不是新决策）。本 ADR 只表明这些点应在 ADR-0019 的承接里继续修复，不新增决策。
- **`call_api_continue` 返回结构对齐**（API 报告 L9）：单次请求路径，工具循环外。保留现状不改。
- **`execute_tool` 调 `tool._run` 私有方法约定**（API 报告 L10）：跨工具框架边界的接口约定，不属本轮。保留。
- **`_dump_initial_payload` 对 base64 data URL 截断 80 字符**（API 报告 L11）：日志可观测性微调，不属本轮。

## 影响

### 正面

- `call_api` 主函数从 ~375 行降到 ~80 行编排，4 条退出路径可单测——补齐 `call_api` 当前的零单测盲区
- `_save_conversation_log` 重复代码消去 ~50 行；`_full` 的 `except: pass` 隐患消除
- `test_clean_md_pipeline` 与生产链路单一真源，根治"平行复制"导致的退化；测试范围从仅历史 1 学科延伸到 7 学科全覆盖
- `BASH_TIMEOUT` 上提为模块级常量，散落硬编码消除

### 负面 / 风险

- **`LoopResult` 引入新类型**——但**对外 dict 字段面冻结**（C2）：`call_api` 返回 6 key、`call_api_continue` 返回 2 key 严格不变；调用方（defaults.py / format_enforcement / smart_split）对 key 的读取不受影响。改造点在内部，外部不可见。
- **`generate_clean_md` 抽公共函数**改变了 `docx_format_enhancer` 的对外 API；新增 `repl` 参数是学科差异的保留载体——`base_subject` 仍传 `self._clean_bold_replacement`，7 学科各自行为**逐字不变**。唯一调用方是 `base_subject._write_problems_to_dirs`，单点改造。
- **BashTool 安全加固不在本 ADR**：原方案被剥离到独立安全议题；本 ADR 仅做 `timeout` 常量化（数值不变），BashTool 执行行为零变化。

### 实施顺序约束

1. **C1 + C2 + C3 必须一起落地**：`LoopResult` 类型 + 4 个抽取函数 + `_save_conversation_log` 合并是一个原子重构切口。先做 C2 类型，再 C1 拆函数，最后 C3 合并 save_log（同时扫尾 `_full` 的 except）。
2. **C5 在 C1 之前或并行**：`generate_clean_md` 是独立的清洗小重构，不依赖 call_api。可与 C1 并行，先做也行——作为重构前热身 + 低风险切口。
3. **C4 BashTool 仅提超时常量**与 C1 完全解耦，单点改造零风险；安全加固议题已剥离到独立 ADR，本 ADR 不涉及。