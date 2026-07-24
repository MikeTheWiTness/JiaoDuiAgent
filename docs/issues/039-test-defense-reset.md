# Issue 039：测试防线复位 —— 全绿 + CI + 高危盲区回归锁

**关联 ADR**：[ADR-0019](../adr/0019-architecture-review-fixes.md)（决策 4/5/6/7）

---

## What to build

让测试套件恢复「全绿才可信」的信号价值。当前 593 通过 / 20 失败，红灯已常态化；本 issue 完成后，`pytest` 本地与 CI 均为 0 失败，且后续提交由 CI 强制保持。

### 1. 陈旧测试逐个处理（13 个）

- `test_prompt_quality.py`：断言对象从已废弃的 `<problem>` 标记改为 `###### 单元开始/结束 ######`（ADR-0018 新行为）
- `test_math_v3_standalone.py`×5：适配 ADR-0017 之后的行为（如 `show_knowledge_option=False`、prompt 结构现状）
- `test_excerpt_extraction.py`×1：改为断言 n-gram 密度算法的真实契约（旧 difflib margin 算法已被替换）
- `test_body_segment.py`×5：依赖 `output/拆题结果/` 本机数据目录，加数据缺失 skip 守卫

### 2. 机器绑定测试加守卫（8 个）

- `test_math_pdf.py`×8：硬编码 `bundled_texlive/bin/windows/xelatex.exe`，加「环境不存在则 skip」守卫（或移入 pytest.ini ignore 并注明原因）

### 3. 仿冒测试改真测（2 处）

- `tests/test_default_proofread_one.py`：删除测试内复刻的实现，改为 import `core.defaults` 真实函数断言
- `tests/test_chemistry_balance.py`：`_parse_formula` 改为 import 真实模块，不再测拷贝

### 4. 最小 CI

- 新增 GitHub Actions workflow：push/PR 时安装依赖并运行 `pytest`
- 注意 Windows 专属依赖（bundled texlive）在 Linux runner 上由决策 2 的 skip 守卫兜住

### 5. 高危盲区回归锁（2 个独立锁）

- `core/parsing.py`：`save_proofread_json` 落盘单测（`_校对数据.json` 是 AGENTS.md 点名的关键中间产物）
- `.skip_proofread` 跨层契约测试：`split_post_utils` 写入方 × UI 读取方的协议一致性

（format_enforcement 与 `_is_unit_dir` 的回归锁分别随 Issue 040、043 交付）

## Acceptance criteria

- [ ] `pytest` 本地全绿（0 failed，skip 均有明确理由）
- [ ] CI workflow 在 push 时运行并通过
- [ ] `test_default_proofread_one.py` / `test_chemistry_balance.py` 直接断言真实实现（grep 无复刻代码）
- [ ] `parsing.py` 有落盘单测
- [ ] `.skip_proofread` 写入/读取协议有契约测试
- [ ] pytest.ini 的 ignore 列表与 skip 理由有注释说明

## Blocked by

- 无 — 可立即开始
