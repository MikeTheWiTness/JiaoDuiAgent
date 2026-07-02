# Issue 017：Session 持久化（中断恢复）

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 8：无 Session 持久化

## What to build

实现正式的 session 状态文件，记录校对进度，使崩溃或关机后可从中断点恢复，替代当前靠检查已有 `_校对报告.md` 来跳过已完成题目的脆弱方式。

**问题**：校对中断（崩溃、关机、手动停止）后，只能靠检查已有 `_校对报告.md` 来判断哪些题目已完成。没有正式的 session 状态文件，无法精确恢复进度，也无法区分"已完成"和"正在校对中"的状态。

**修复方向**：
1. 定义 Session 状态结构：
   - session_id、start_time、last_update
   - 题目列表 + 每题状态（pending / in_progress / completed / failed）
   - 已完成题目的输出路径
2. 在 `default_proofread_one` 开始/结束时更新状态
3. 启动时检测已有 session 文件 → 提示用户是否继续
4. 异常退出时状态至少标记当前题目为 failed（而非丢失）

**涉及文件**：
- `core/defaults.py` — session 状态读写协调
- `core/api_client.py` — 校对中断时的状态标记
- 新增 `shared/session.py` — Session 状态管理

## Acceptance criteria

- [ ] Session 状态文件以 JSON 格式持久化，包含题目列表和每题状态
- [ ] 校对开始/结束时自动更新 session 状态
- [ ] 启动时检测未完成的 session，提示用户选择继续或重新开始
- [ ] 异常退出（崩溃/关机）后，至少有最近一次保存的状态可恢复
- [ ] 状态文件写入使用原子操作（先写临时文件再 rename），防止写入中途崩溃导致文件损坏

## Blocked by

None - 远期需求驱动，可随时独立开始
