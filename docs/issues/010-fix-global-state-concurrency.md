# Issue 010：修复全局状态污染（text_nav_tools 并发安全）

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 1：全局状态污染

## What to build

修复 `shared/text_nav_tools.py` 中模块级全局单例 `_current_text` 导致的并发竞态条件。

**问题**：`_proofread_thread` 使用 `ThreadPoolExecutor` 并发校对多道题，所有线程共享同一个 `_current_text`。线程 A 校对题目 X 时，线程 B 可能已将 `_current_text` 覆盖为题目 Y 的文本，导致 A 的 `locate_paragraph` / `read_section` 工具返回错误位置的段落。

**修复方向**：将 `_current_text` 从模块级全局变量改为线程局部存储（`threading.local()`），或作为工具实例属性注入，确保每个线程有自己独立的文本上下文。

**涉及文件**：
- `shared/text_nav_tools.py` — 核心修改：全局变量 → `threading.local()`
- `core/api_client.py` — 更新 `_set_nav_text` 调用点（约第 268 行）
- 新增并发测试

## Acceptance criteria

- [ ] `text_nav_tools.py` 中不再使用模块级 `global _current_text`，改为线程安全的存储方式
- [ ] `call_api` 中 `set_current_text` 调用点适配新的线程安全接口
- [ ] 并发测试：两个线程同时校对不同文本，各自调用 `locate_paragraph` 返回正确段落，不互相干扰
- [ ] 现有文本导航工具测试全部通过，无回归

## Blocked by

None - 可立即开始
