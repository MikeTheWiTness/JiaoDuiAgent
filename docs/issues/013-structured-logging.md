# Issue 013：日志结构化升级

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 5：日志无结构化

## What to build

将 `core/logging_utils.py` 的纯字符串 `log()` 函数升级为标准 `logging` 模块，引入日志级别、时间戳、模块名，使排查问题时可精确过滤而非纯文本搜索。

**问题**：当前 `log()` 只是字符串透传到 UI 日志面板，无日志级别、无时间戳、无模块名。排查问题时只能全文搜索关键字，效率低且容易遗漏。

**修复方向**：
1. 引入 Python 标准 `logging` 模块，配置格式化器（时间戳 + 级别 + 模块名 + 消息）
2. 保留 UI 日志面板输出（通过自定义 Handler 桥接到现有 UI `_log_func`）
3. 同步落盘到日志文件（按日期滚动）
4. 将现有 `log("msg")` 调用逐步迁移为 `logger.info()` / `logger.warning()` / `logger.error()`
5. 中间产物日志（`_校对报告.md`、`_API对话记录.md` 等）也加入时间戳和来源模块标记

**涉及文件**：
- `core/logging_utils.py` — 核心改造
- `core/api_client.py` — 迁移 log 调用
- `core/defaults.py` — 迁移 log 调用
- 其他使用 `log()` 的模块 — 渐进迁移

## Acceptance criteria

- [ ] 日志输出包含时间戳、级别（INFO/WARNING/ERROR）、模块名
- [ ] 日志同时输出到 UI 面板和磁盘文件
- [ ] 磁盘日志按日期滚动，单文件不超过 10MB
- [ ] 现有 `log()` 接口保持兼容（或提供明确迁移指南）
- [ ] 中间产物文件末尾包含生成时间戳和来源模块

## Blocked by

建议在 Issue 011（API 用量追踪）和 Issue 012（错误处理分层）之后进行——它们会新增 log 调用点，先让它们落定再统一升级日志框架。
