# Issue 040：call_api 断链修复 —— 复活格式修正与智能分割

**关联 ADR**：[ADR-0019](../adr/0019-architecture-review-fixes.md)（决策 1/2/3）

---

## What to build

ADR-0012 将 `call_api` 改为 `ctx` 签名后，三处调用方未迁移，必抛 TypeError 并被 `except Exception` 吞掉——「LLM 格式修正」与「智能分割」两个功能实际从未工作。本 issue 修复断链并建立防再犯机制，完成后两个功能真实可用。

### 1. 删除死模块

- 删除 `shared/knowledge_split.py`（576 行，生产零调用）及 `tests/test_knowledge_split.py`

### 2. SessionContext 工厂

- `core/session_context.py` 新增 `SessionContext.from_credentials(api_url, api_key, model, output_dir=..., ...)` 工厂方法

### 3. 迁移两处活调用

- `core/format_enforcement.py` 的 `_bash_format_fix`：经工厂构造 ctx，按新签名调 `call_api`
- `shared/smart_split.py` 的 `_llm_call`：同上
- 修复后验证：格式不合规的校对输出能触发 LLM 格式修正；UI 选「智能分割」真实产出多单元拆分

### 4. 异常吞掉全扫（~10 处）

所有 `except` 只记 message 或完全 pass 的位置，改为 `log()` 输出完整 traceback + 上下文摘要（函数名/输入摘要），落实 AGENTS.md 硬性要求。已知位置：

- `core/api_client.py`（execute_tool 吞工具异常、tool arguments JSONDecodeError 静默）
- `core/defaults.py`（写 `_校对报告.md`/存档失败多处 pass、图片 base64 失败 continue）
- `ui/default_app.py`（`_proofread_thread` 兜底 except 无 traceback）
- `core/env_config.py`（.env 读取静默）
- `shared/physics_tools.py`（`_物理求解.md` 落盘静默）

### 5. 回归锁

- `core/format_enforcement.py` 直接单测：格式不合规 → 修正链路真实被调用（不再只靠被 ignore 的 e2e）

## Acceptance criteria

- [ ] `_bash_format_fix` 与 `smart_split` 使用 `SessionContext.from_credentials` 按新签名调用，无 TypeError
- [ ] 智能分割端到端可用（LLM 输出单元标记 → 多单元目录）
- [ ] `shared/knowledge_split.py` 及其测试已删除，全仓无残留 import
- [ ] 审查列出的 ~10 处异常吞掉全部改为 log + traceback + 上下文
- [ ] format_enforcement 有直接单测且通过
- [ ] `pytest` 保持全绿

## Blocked by

- Issue 039（测试防线复位 —— 需要全绿安全网验证修复）
