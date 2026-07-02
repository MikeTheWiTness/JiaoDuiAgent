# Issue 018：测试架构整理（pytest.ini + CI + 覆盖率）

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 9：测试架构零散

## What to build

统一 30+ 测试文件的运行方式，添加 `pytest.ini` 配置、CI 流水线和覆盖率要求，建立可持续的测试纪律。

**问题**：当前测试架构零散：
- 无 `pytest.ini`，测试运行依赖默认配置
- 无 CI 配置（GitHub Actions 等），每次靠人工运行
- 无覆盖率要求，无法衡量测试充分性
- `unittest.TestCase` 和独立脚本混用，风格不统一

**修复方向**：
1. 添加 `pytest.ini`：配置测试目录、默认参数、覆盖率插件
2. 统一测试风格：逐步将 `unittest.TestCase` 迁移为 pytest 风格（`assert` 替代 `self.assertEqual`）
3. 添加 `.github/workflows/test.yml`：push/PR 触发自动运行测试
4. 设置最低覆盖率阈值（建议 60% 起步，逐步提升）
5. 添加 `conftest.py` 共享 fixture

**涉及文件**：
- 新增 `pytest.ini`
- 新增 `.github/workflows/test.yml`
- 新增 `tests/conftest.py`
- `tests/*.py` — 渐进迁移

## Acceptance criteria

- [ ] `pytest.ini` 存在并配置了测试目录、覆盖率插件、最低覆盖率阈值
- [ ] `pytest --cov=core --cov=shared --cov-report=term` 可正常运行
- [ ] GitHub Actions CI 在 push/PR 时自动运行测试
- [ ] CI 失败时 PR 被阻止合并
- [ ] 至少 3 个现有 `unittest.TestCase` 文件迁移为 pytest 风格作为示例

## Blocked by

None - 远期需求驱动，可随时独立开始
