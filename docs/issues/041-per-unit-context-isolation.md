# Issue 041：每单元状态收编 —— 消灭共享 ctx 改写与全局 _api_config

**关联 ADR**：[ADR-0019](../adr/0019-architecture-review-fixes.md)（决策 8/9/10）

---

## What to build

并行校对时，每单元的运行状态（output_dir、max_loops、求解工具配置）存放在跨线程共享位置，导致三个 bug 同根并发：`_API对话记录.md` 多线程互覆、`ctx.max_loops=0` 污染后续单元、物理/化学 `_物理求解.md`/`_化学求解.md` 竞态写错目录。本 issue 把每单元状态收编到单元作用域，三个 bug 一次消除。

### 1. 每单元派生 ctx 副本

- 校对 worker 入口（`ui/default_app.py` 的 `_proofread_thread` 内）：每单元 `dataclasses.replace(ctx, output_dir=q_dir)`
- `interrupt_event` 为引用复制，天然保持全局共享（中断仍全批次生效）
- 效果：`_API对话记录.md` 写入各自单元目录，多线程不再互覆；`_校对报告.md` 头部指向的对话记录文件真实存在；中间产物存档断链自愈

### 2. SessionContext frozen 化

- `@dataclass(frozen=True)`：把「不可变」从 docstring 注释变成运行期约束
- 全仓唯一改写点（决策 3 要删的那行）删除后 frozen 安全

### 3. 删除 max_loops 污染源

- 删除 `core/defaults.py` 非 ReAct 分支里的 `ctx.max_loops = 0`：`tools=[]` 时 payload 无 tools 字段，工具循环本就不会启动，该行是冗余保护

### 4. 求解工具配置改 thread-local

- `shared/physics_tools.py`、`shared/chemistry_tools.py`：模块级全局 `_api_config` dict 改为 `threading.local()`，照抄 `shared/bash_tool.py:213` 已有模式
- `set_physics_api_config` / `set_chemistry_api_config` 签名不变
- 两文件的复制粘贴大重复不在本 issue 范围（归后续 C4）

## Acceptance criteria

- [ ] 并行校对 N 个单元，各单元目录下 `_API对话记录.md` 内容完整且互不覆盖
- [ ] `_校对报告.md` 头部引用的对话记录文件真实存在
- [ ] `SessionContext` 为 frozen dataclass，任何字段改写运行期报错
- [ ] 前置参考注入的单元之后，后续单元工具循环不受影响（max_loops 不被污染）
- [ ] 并行校对物理/化学多单元，求解文件写入各自单元目录
- [ ] `pytest` 保持全绿

## Blocked by

- Issue 039（测试防线复位）
- Issue 040（异常全扫与 session_context 工厂改动同文件，避免冲突）
