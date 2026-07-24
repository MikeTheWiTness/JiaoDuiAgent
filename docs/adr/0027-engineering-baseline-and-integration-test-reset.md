# ADR 0027：工程化基线（ruff + pre-commit + pyproject + 锁文件）+ 集成测试复位（markers 取代 --ignore + 双平台 CI）

**状态**：已实现（commit 298498a）
**日期**：2026-07-23（2026-07-24 修订）
**实现日期**：2026-07-24
**决策者**：MikeTheWiTness
**关联**：[[ADR 0019 架构审查修复]](0019-architecture-review-fixes.md)、[[ADR 0022 UI 编排下沉]](0022-ui-orchestration-sink-to-core.md)

## 范围原则

本 ADR 是工程化设施与测试基础设施的优化，**不改变测试覆盖范围**——`markers` 取代 `--ignore` 前后，被默认排除的文件集合**完全一致**（原 5 个 `--ignore` 文件继续被默认排除，且不在不存在的死规则 `test_e2e_knowledge.py` 中）。

CI 双平台矩阵仅是工程化强化，单元/快测试均能通过现状的本地 `pytest` 跑通——本 ADR 不修改现有任何 `test_*` 函数体的断言。

---

## 背景

仓库的工程化基线几乎为零，意味着红线缺乏强制力，自 ADR-0019 C6.3「红线机制——全绿 + 最小 GitHub Actions CI」落地后仍脆弱。审查发现的具体问题：

1. **缺失设施**：无 ruff/flake8、无 pre-commit、无 `pyproject.toml`、无锁文件（无 `requirements.lock` / `poetry.lock` / `uv.lock`），无 mypy/pyright。
2. **`requirements.txt` 6 行全 `>=` 下限**，且**漏列实际依赖**：Pillow（`shared/image_utils.py`、`shared/sympy_tools/templates.py` 用）、lxml（docx 间接，但显式声明更稳）、playwright（`shared/shidianguji_playwright.py` 用）。CI 在 Install 步骤里 `pip install ... || true` 兜底——依赖没装上 CI 也可能"绿"。无锁导致可复现性差。
3. **CI 与本地 pytest 过滤清单双轨漂移**：`pytest.ini` 与 CI 各自一份 `--ignore` 列表，CI 多忽略不存在的 `tests/test_e2e_knowledge.py`——死规则。
4. **平台环境不符**：CI `ubuntu-latest` + Python 3.11，README/packaging.md 声明目标为 Windows 10 + Python 3.12，环境不一致——GUI 用 tkinter 在 ubuntu runner 跑不起来 e2e。
5. **markers 失效**：`pytest.ini` 已定义 `--strict-markers` + `slow/network/e2e` markers，但 markers 一次未被使用，集成测试文件被 `--ignore` 永久排除，分层纪律流于形式。
6. **伪装 e2e**：`tests/test_e2e_agent_pipeline.py` 文件名带 `test_e2e`，实际只有 `def main()`（86行）+ `if __name__ == '__main__'`，无 `def test_*`，是 CLI 脚本。靠 `pytest.ini --ignore` 躲过 pytest，是为虚增。

## 决策

### C1：工程化基线全引入（ruff + pre-commit + pyproject + 锁文件），mypy 暂不调

- **`pyproject.toml`**：声明包元信息（项目名、Python 版本约束、入口点）。承载 `ruff` 配置，承载包声明避免 setup.py/cfg 多源。
- **`ruff`**：取代 flake8/black。`pyproject.toml` 里配 `[tool.ruff] line-length = 100` + `[tool.ruff.lint] select = ["E", "F", "W", "I", "UP"]`。这是审查报告里的 P2 "无 lint 配置" 的直接补足。
- **`pre-commit`**：项目自带 `setup-pre-commit` skill 可一键生成。`.pre-commit-config.yaml` 至少跑 `ruff check` + `ruff format --check`。提交时强制，关闭"无声退化"。
- **锁文件**：迁移到 `pyproject.toml` + `uv` 或 `pip-tools`，生成 `requirements.lock`（或 `uv.lock`）。锁文件把 `requests/pydantic/sympy/ddgs/python-docx` 锁到确定版本，并**显式补上漏列的 Pillow、lxml、playwright**。装依赖一律 `pip install -r requirements.lock`（或 `uv sync`），不再用 `pip install ... || true` 兜底——`|| true` 必须删除，依赖装不上 CI 必须报红。
- **mypy/pyright 不引入**：当前代码类型注解覆盖不完全，一并上 mypy 调用大量类型错误需要多波提交修复，拖升 CI 但收益不确定。留给日后基础类型注解齐了再立 ADR。

### C2：CI 依赖安装去吞错

CI workflow 里所有 `pip install ... || true` 与 `2>/dev/null || true` 都删。依赖装不上让 CI 直接报错——这是 C1 锁文件机制能成立的前提，也防止"CI 假绿"。

### C3：markers 取代 `--ignore` + 真集成可触发（默认跑集合保持一致）

- `pytest.ini` 与 CI workflow 删除 `--ignore` 硬列表（含死规则 `test_e2e_knowledge.py`）。
- 集成测试文件按维度打 markers：原 `--ignore` 里的文件改为 `@pytest.mark.e2e` / `@pytest.mark.network` / `@pytest.mark.slow`。`pytest.ini` 保留 markers 定义与 `--strict-markers`。
- **关键：`pytest.ini addopts` 必须默认加 `-m "not e2e and not network and not slow"`**（2026-07-24 审查加）——保证本地无参数 `pytest` 默认跑的文件集合与现状（被 `--ignore` 永久排除 5 个文件）**完全一致**。原 `--ignore` 永久排除的那 5 个文件在本 ADR 落地后，对本地无参数 `pytest` **仍然默认不被跑**——开发者需 `pytest -m e2e` 显式覆盖。这是取消"markers 取代 --ignore"会改变本地默认行为的修正。
- CI 默认跑同样的 `pytest -m "not e2e and not network and not slow"`（与本地默认一致）；CI 单元与快测试在不同平台间行为一致。
- 手动跑全或跑某维度时用 `pytest -m e2e`，真集成测试一次不被永久排除（在显式调用下可跑），**恢复分层纪律**——这是 ADR-0019 C6.3"红线机制"被软化后的复位。

### C4：CI 双平台矩阵

` ubuntu-latest`没法跑 GUI tkinter e2e；但是单元 + 非集成可全平台跑。CI 由单平台改：

- `unit-and-fast`：`ubuntu-latest` + Python 3.12，跑 `-m "not e2e and not network and not slow"`。
- `windows-latest` + Python 3.12：同一命令。Windows 是目标平台，CI 帮帮忙维持目标平台绿灯。

不强行让 windows runner 跑 e2e（GUI 自动化跨平台 flake 多，CI 才是负担）；只跑 unit + fast 两类。e2e/network/slow 标 marker 的集成测试靠手动触发或周末跑。

### C5：`test_e2e_agent_pipeline.py` 迁移到 scripts/

该文件实际是 CLI 工具脚本（`def main()` + `if __name__ == '__main__'`，无 `def test_*`），伪装 e2e 浪费 CI 上注意力。迁到 `scripts/test_e2e_agent_pipeline.py`（或 `scripts/run_e2e_agent_pipeline.py`），与 `tests/` 物理分离。`pytest.ini` 里不再需要为它继续豁免（C3 删 `--ignore` 时自动顺带处理）。

顺手：审查报告 P3 的 `tests/diagnose_diff_paths.py`、`tests/preview_react_prompt.py`、`tests/_search_results/` 类似非测试产物也一起迁到 `scripts/` 与 `.gitignore`（`tests/_search_results/`）——这些与 ADR H/I 清理支线有重合，本支线负责把它们从 `tests/` 拨出去，详细 .gitignore 补列留给清理支线（见 ADR 0028 or 后续清理清单）。

## 明确不做（本支线范围外）

- **mypy/pyright 全调**：见 C1 阐述，留给日后。
- **`AGENTS.md` / `CLAUDE.md` / `Trae.md` 三套约束合并**：归 [[ADR 0028 清理与流程约束]]（待写）的清理与流程约束。
- **`requirements.txt` 退役到纯 `pyproject.toml`管理**：pyproject lock 共存，但对外正式路径转 `pip install -r requirements.lock` / `uv sync`。`requirements.txt` 暂保留兼容外部使用习惯，不退役。
- **black/isort 独立**：ruff 已经集成等价能力，不引入 black/isort。
- **CI full e2e matrix**：跨平台 e2e 自动化是更高位阶的工程化，本支线只让 e2e "可手动触发、CI 不默认跑"，不进一步投入。

## 影响

### 正面

- ruff 接管 lint，pre-commit 接管提交点强制；CI 单元测试 + lint 都跑
- 锁文件 + Pillow/lxml/playwright 显式声明，CI 取消 `|| true` 兜底——依赖装不上即报红
- markers 取代 `--ignore` 把真集成从"永久禁用"恢复为"按需可跑"，分层纪律复位
- Windows-latest 进 CI matrix，目标平台绿灯被守护
- `test_e2e_agent_pipeline.py` 迁到 scripts/，与 tests/ 物理分离，CI 不再误扫

### 负面 / 风险

- **pre-commit 入门成本**：第一次装 pre-commit 钩子的人本地要 `pre-commit install`，旧贡献者首次提交可能被拦下。缓解：在 README/dev 文档里加一行 install 指引；`setup-pre-commit` skill 可一键安装。
- **CI Windows 跑得更慢**：windows-latest CI 比 ubuntu 慢约 2×。两条流水线并行即可，不存在串行等待。可接受。
- **markers 切换的横向 + 不完美**：原 5 个 `--ignore` 文件改 marker 后，CI 默认 `-m "not ..."` 与原 `--ignore` 行为等价；但开发者本地若不写 `-m` 会不小心跑起 integration。缓解：写 CI workflow 之外，在 README/dev 文档里交代"本地默认全跑 vs CI 默认快测试"。
- **playwright 进 requirements.lock 会增 CI 依赖安装时间**：playwright 主包不大，其 driver 需 `playwright install chromium`——CI 是否自动安装 driver 由本支线也不开展，playwright e2e 走手动维度 (`-m network`)，**driver 装由开发者自己装**。锁文件锁的是 Python 包链，不锁 driver。

### 实施顺序约束

1. **C1 + C2 同步**：pyproject + 锁文件 + 去 `|| true` 是工程化基线的核，必须同一 PR；其它设施可以此为前提铺。
2. **C1 ruff 引入需收拾现有代码**：ruff 一上线会发现既有违规（如 P3 L1 的多个 `import json, time, re, os` 同行、未使用 import）。本支线接手"清理被 ruff 标红的最小违规"——单 import、未使用 re 等；不挑长函数类的复杂违规（那是 latex/pdf call_api 等 ADR 范畴）。
3. **C3 markers 切换**必须在 C1 ruff 切换之后或同一 PR——否则 `test_e2e_knowledge.py` 死规则可能被 ruff 误识。先 ruff 后 markers 顺手清，比较干净。
4. **C4 双平台**与 C3 平行可，但要求 CI 在两平台都能跑 C1 锁文件 install 成功；有平台差异时按 windows 实际兼容性补，pyproject `python_requires = ">=3.12"` 守住基线。
5. **C5 scripts/ 迁移**最后做或与 C3 同步——纯文件迁移，零逻辑改动。