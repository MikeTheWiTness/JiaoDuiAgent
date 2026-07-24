# ADR 0022：UI 编排下沉到 core（ConversionService + ProofreadService）

**状态**：已接受（待落地，独立支线）
**日期**：2026-07-23（2026-07-24 修订：C2 不强行删 `task_interrupt` bool，保留作 mirror）
**决策者**：MikeTheWiTness
**关联**：[[ADR 0019 架构审查修复]](0019-architecture-review-fixes.md)、[[ADR 0013 UI 模式重设计]](0013-ui-mode-redesign.md)

## 范围原则

本 ADR 是 UI 编排逻辑下沉到 core 的重构优化，**不改变校对/转换的总行为**——所有用户可见交互流程、输出文件结构、并发调度顺序、缓存命中决策与现状逐字一致。

---

## 背景

`ui/default_app.py` 1260 行单文件，把转换/拆分/校对/PDF/报告/缓存/并发编排全部塞进 UI 控件类里：

- `_conversion_thread`(769-1015) 246 行：文件后处理编排（fix_latex_escapes / clean_md_file / normalize_option_spacing / post_process_md_zw 等）、批注占位注入与回写、split_lecture/split_exam 调度、自由校对组装。
- `_proofread_thread`(1044-1231) 187 行：题目目录扫描 + 正则识别、缓存命中判断、SessionManager 初始化与进度持久化、ThreadPoolExecutor 批次调度、结果聚合与 PDF 汇总。
- 全 `tests/` 无一处 `from ui`/`import ui`——**UI 整个零测试**，所有这些业务逻辑都不可自动化验证。
- 中断用 `self.task_interrupt`(bool，65 行) + `self._interrupt_event`(threading.Event，66 行) 双标志表达同一意图，跨线程非原子写，`interrupt_task` 同时改两处（1038-1042），而 `_proofread_thread` 读 `task_interrupt` 5 处又另起 `interrupt_event.clear()`（1053），存在竞态。
- 目录合法性正则 `第\d+题|板块\d+|单元\d+` 在 `default_app.py:672`(select_pdf_folders) 与 `_proofread_thread:1075-1083` 两处各定义一份；ADR-0019 C3.14 修了 `_is_unit_dir` 识别 `单元N/`，但只在 core 一处，UI 两处仍各写一份，DRY 与可测双败。

ADR-0019 C5 已明确把"校对编排从 UI 下沉 core 统一设计"标为后续单独立项，不在 ADR-0019 范围内零散修补。本 ADR 兑现这一预告。

## 决策

### C1：编排层形态——服务类 + 进度回调

**选择**：`core/pipeline_service.py` 暴露两个服务类（`ConversionService` / `ProofreadService`），各带 `run_conversion(req)` / `run_proofread(req)` 方法。**不引入 generator 事件流**——现有 tkinter 是 after-loop 同步消费模型，与 generator-iterator 消费侧节奏不符，重写 UI 消费侧代价过大。**也不用纯函数 + 不可变 DTO 全状态对象**——丢弃服务类内襄会让"批次管理、缓存命中"等内部状态散到调用方，得不偿失。

服务类通过**构造期注入回调**上报事件：

- `on_progress(...) -> None`：进度更新（当前题号、批次进度比例）
- `on_log(...) -> None`：日志事件（调用 `core.logging_utils.log`，与既有日志面板对接）

回调只上报事件，不持有 UI 引用。service 把 `on_log` 委托到 `core.logging_utils.log`，无需 UI 中转。

### C2：下沉范围——双服务并行 + 目录识别到 core

**两个 service 都抽**，不留半截：

1. **`ConversionService.run_conversion(req: ConversionRequest) -> ConversionResult`**：承载 `_conversion_thread` 全部业务（文件后处理、批注占位注入/回写、split_lecture/split_exam 调度、自由校对组装）。
2. **`ProofreadService.run_proofread(req: ProofreadRequest) -> ProofreadResult`**：承载 `_proofread_thread` 全部业务（目录扫描、缓存命中、ThreadPoolExecutor 并发、聚合、PDF 汇总）。
3. **目录识别抽到 `core/unit_detect.py`（新模块）**：
   - `is_unit_dir(d: Path) -> bool`——单一真源，识别 `第N题` / `板块N` / `单元N`，供 `ProofreadService` 与 UI `select_pdf_folders`/`select_root_for_proofread` 同时复用。
   - ADR-0019 C3.14 在 `core/defaults.py` 里修过 `_is_unit_dir`——把这版逻辑上移到 `core/unit_detect.py` 作为单一源，`defaults.py` 改为 import 而非自己实现。
4. **`_export_paper_report`(1233-1242)、文件名净化 `safe_name` 纯逻辑** 顺手抽到 service 或 `core/paths.py`，让纯逻辑可单测。

**统一中断**：service 入口统一接 `threading.Event` —— 既有 `SessionContext.interrupt_event` 已经把 interrupt 暴露为 Event，`ProofreadService` 与 `ConversionService` 同时持有"会话级事件"和"UI 全局中断事件"，按场景查 `is_set()`。

**保留 `task_interrupt` bool 作 mirror（2026-07-24 审查改）**：UI 不强行删除 `default_app.py:65` 的 `self.task_interrupt` bool——保留它作 mirror（UI 仍可继续写它），但 `ProofreadService` / `ConversionService` 入口统一接 Event，不再读 bool。理由：删 bool 改 Event 是表面字段变更，对纯优化 ADR 范围溢出；保作 mirror 让既有外部引用的隐性零破坏，主路径中断行为与现状等效（中断触发 → service 通过 Event 看到 → 立即 return）。

**明确不并入本支线**：UI 的状态字段（`file_list`/`proofread_list`/`proofread_result`/`free_text`/`free_images`/`free_files`/`subject_app`）仍保留在 UI 作为裸实例字段。**不强行做整体 `PipelineState` 不可变 dataclass 化**——那是更大的改革，留给后续单独立项；本支线只做编排下沉，不做 UI 全状态重构。

### C3：Service 测试覆盖

`core/pipeline_service.py` 写完后必须配套单测，覆盖：
- `run_proofread` 的缓存命中 / 未命中 / 部分命中分支
- `batch_size` 解析与降级
- `interrupt.is_set()` 中途打断
- `run_conversion` 的 split_lecture/split_exam 调度分支
- `core/unit_detect.is_unit_dir` 边界（题号/板块/单元；非标准名）

UI 仍无单测（tkinter 渲染类组件不在测试目标内），但所有业务逻辑脱离 UI 后即触达测试。

---

## 明确不做（本支线范围外）

- **整体 `PipelineState` 不可变 dataclass**：UI 全状态对象化改革，留给后续单独立项。
- **`SessionContext.from_credentials` 默认值不一致**（`max_loops=3` vs dataclass 20）、`config_loader._config_cache` 无锁：归到 [[ADR 0023 配置三轨合并]](0023-config-source-unification.md)（待写）。
- **`default_app.py` 全文件 1260 行的最终瘦身**：service 抽出后 default_app 仍约 ~700 行（控件装配 + 文件选择对话框 + 状态字段 + 线程启动器），进一步拆需等 service 稳定，不在本支线。
- **batch_size 从 UI config 推断**：当前默认值逻辑在 `_proofread_thread` 内，下沉到 service 后顺手变量化，但默认值本身不动。

## 影响

### 正面

- `_conversion_thread`(246 行) 与 `_proofread_thread`(187 行) 不再属于 UI，UI 退化为控件装配 + 线程启动器
- `core/pipeline_service` 全模块可单测，根治"UI 整个零测试"盲区最高风险面
- 中断单源，消除双标志竞态
- `core/unit_detect.is_unit_dir` 统一三处实现（defaults / UI / select_pdf_folders），单一真源
- `select_pdf_folders` 与 `_proofread_thread` 的目录识别正则 DRY 消重

### 负面 / 风险

- **UI 改写面积不小**：两个 thread 函数 ~433 行业务移走，UI 线程启动器改写为"创建 req + 注入回调 + submit service.run_*"。改写期间分支较大，建议在该支线用一个独立 commit 完整切换，不做夹生过渡。
- **回调接口不当时会重新耦合 UI**：`on_progress`/`on_log` 若参数里夹带 tk Widget 引用，则 service 又被绑到 UI——故回调签名约束为"纯数据参数"，service 一律不知道 tk。这条纪律写入 ADR 实现章节。
- **`safe_name` 等 UI 内嵌纯逻辑抽走后**，UI 调用点需更新——但这类纯函数本来就应可单测，挪到 service 是正向。