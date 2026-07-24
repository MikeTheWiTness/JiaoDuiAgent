# ADR 0025：pdf_compiler 拆四函数 + 诊断去重

**状态**：已接受（待落地，独立支线）
**日期**：2026-07-23（2026-07-24 修订：C1 补 "texmf_root 为 None 时 `_build_compile_env` 返回 None 不传 env" 行为不变约束）
**决策者**：MikeTheWiTness
**关联**：[[ADR 0024 latex_generator pipeline 重构]](0024-latex-generator-pipeline-refactor.md)、[[ADR 0021 call_api 重构]](0021-call-api-refactor-bashtool-safety-test-degradation.md)

## 范围原则

本 ADR 是纯重构优化，**不改任何编译行为**。所有 subprocess 调用、env vars 集合、超时数值、命令参数、错误消息文本与现状逐字一致。

---

## 背景

`shared/pdf_compiler.py:compile_to_pdf`（168-386）~220 行单函数，承担：

- 建临时目录 + 复制字体/格式资源
- 找 xelatex 可执行路径
- **组装 ~15 个 env vars**（253-281）——硬编码字符串拼接，无法单测
- cmd1：xelatex 编译 → `subprocess.run` → 失败诊断（295-306）
- cmd2：xdvipdfmx 或二轮编译 → 失败诊断（350-377）
- 复制生成的 PDF 到输出目录
- 清理临时目录

诊断逻辑在 295-306 与 350-377 **两处重复**，都是"取 `!` / `fatal` / `Error` 行 + 尾部 10/15 行" 拼成 `--- DIAGNOSTIC ---\n...\n--- LOG TAIL ---\n...`，仅前缀信息不同。

`timeout=120` 在 248 与 317 两处硬编码；`shared/bash_tool.py:50` 的 `timeout=30` 又是另一处硬编码——无统一配置点（与 ADR-0021 C4 提到的 `BASH_TIMEOUT` 同源，是审查报告的 P2 散落常量问题）。

## 决策

### C1：四函数抽取 + 诊断单一源

`compile_to_pdf` 拆四个函数，主函数仅编排：

1. **`_build_compile_env(texmf_root, tmpdir, fonts_tmp) -> dict | None`**：组装 ~15 个 env vars。返回纯 dict，可单测（断言 `TEXINPUTS` 含目标路径、`TTFONTS` 在字体目录等）。

  **严格行为不变约束（2026-07-24 审查加）**：阅读现状 `pdf_compiler.py:251-274` 发现 env vars 构造只在 `if texmf_root:` 分支内做——**texmf_root 为 None 时根本不传 env**，subprocess 继承父进程 env。所以：
  - `_build_compile_env` 接收 `texmf_root`，**texmf_root 为 None 时返回 None**（而非 `{}`）。
  - 主函数在 `build_env` 为 None 时，**保持 `compile_kwargs` 不含 `env` key**（与现状一致），不强行 `env={**os.environ, **{}}`。
  - `texmf_root` 不为 None 时，`_build_compile_env` 返回的 dict 按现状 `env = os.environ.copy()` 起步、然后逐字段覆盖，与现状逐字一致——**主函数不可改 `subprocess.run` 的调用**（包括 `subprocess.call` vs `subprocess.run` 的差异、`cwd`、`stdout=DEVNULL`、`stderr=DEVNULL`、Windows `CREATE_NO_WINDOW`/`STARTUPINFO` 等）。
  - env vars 字段名与值（含分号、引号、路径拼接顺序）逐字一致。

2. **`_run_xelatex(cmd, log_path) -> tuple[int, str]`**：执行 xelatex 子命令，返回 `(retcode, stdout_stderr)`。隔离 subprocess 调用细节，便于单测时注入 mock subprocess。

3. **`_run_xdvipdfmx(...)` 或第二轮 xelatex**：与 2 同构，承载第二步编译调用。

4. **`_diagnose_log(log_path) -> str`**：从 xelatex 日志提取诊断信息——取 `!` / `fatal` / `Error` 行 + 日志尾部 15 行。两处失败路径（cmd1 与 cmd2）共用此函数，仅靠参数化"前缀信息"区分最终错误消息。

  **严格保留两处原差异（C3 `_format_compile_error` 共用同原则）**：`pdf_compiler.py:295-306` 与 `350-377` 两处的尾部行数、过滤模式、消息前缀文本若存在差异（落地时先比对），不动；两处共用 `_diagnose_log` 与 `_format_compile_error` 后，**各自传入的前缀字符串、retcode 与现状逐字一致**，输出 `RuntimeError(...)` 的消息文本逐字不变。

主函数 `compile_to_pdf` 退化为：
```
tmpdir = ...
fonts_tmp = ...
texmf_root = ...
env = _build_compile_env(texmf_root, tmpdir, fonts_tmp)
retcode, output = _run_xelatex(cmd1, log_path)
if retcode != 0:
    raise RuntimeError(_format_compile_error("xelatex", retcode, _diagnose_log(log_path)))
retcode, output = _run_xdvipdfmx(cmd2, log_path)
if retcode != 0:
    raise RuntimeError(_format_compile_error("xdvipdfmx", retcode, _diagnose_log(log_path)))
shutil.copy(pdf_src, pdf_dst)
```

### C2：统一编译超时常量

`pdf_compiler.py:248,317` 的 `timeout=120` 与 `bash_tool.py:50` 的 `timeout=30`（后者已由 ADR-0021 C4 提为 `BASH_TIMEOUT`）一并上提为模块级常量：

- `pdf_compiler.py`：`LATEX_COMPILE_TIMEOUT = 120`
- `bash_tool.py`：`BASH_TIMEOUT = 30`（ADR-0021承接）
- `api_client.py`：`TIME_OUT = (30, 1800)`（已有，不需改名）

三者并列为仓库内"超时常量三源"——不再散落在函数体内。后续若要统一到 `shared/config.py` / `core/defaults.py`，是 P2 另一 ADR 的事，本支线只做"提为模块级常量"这一最小集。

### C3：失败错误格式函数

抽 `_format_compile_error(stage: str, retcode: int, diagnostic: str) -> str`，承载两处构造 `--- DIAGNOSTIC ---\n...\n--- LOG TAIL ---\n...` 的样板。`stage` 区分 "xelatex" / "xdvipdfmx"。这是 C1 `_diagnose_log` 的互补——`_diagnose_log` 提取日志内容、`_format_compile_error` 包上 RuntimeError 文本，两函数职责正交。

## 明确不做（本支线范围外）

- **全面类型注解**：`pdf_compiler.py` 多函数无类型注解，补注解与拆函数正交，留给日后小补丁。
- **超时常量统一到 `shared/config.py`**：C2 仅做到"提为模块级常量"，三常量在不同模块并列；若要走更远的统一，留给后续 ADR。
- **PDF 编译失败时的恢复路径增强**（如自动追加 `\usepackage{}` 重试）：当前无该需求，不在本支线扩展功能面。

## 影响

### 正面

- `compile_to_pdf` 主函数从 ~220 行降到 ~50 行编排
- env vars 组装、诊断提取两类逻辑从被动 inline 升为可单测函数
- 诊断逻辑两处重复（~50 行）消除为单一源
- `LATEX_COMPILE_TIMEOUT` / `BASH_TIMEOUT` 上提为模块级常量，散落硬编码消除

### 负面 / 风险

- **`_run_xelatex` / `_run_xdvipdfmx` 的 subprocess 隔离需注意**：要避免在抽函数时把 `subprocess.run` 的某些子参数（如 `env`、`cwd`）漏传。落地时分两步：先把 env vars 提取到 dict、subprocess.run 调用点不动；再抽 subprocess 调用。任何一步保持端到端编译测试可跑（既有 `test_math_pdf.py` 等需环境 skip 守卫，见 ADR-0019 C6.4）。
- **mock subprocess 单测**：`_run_xelatex` 真实执行需 xelatex 可执行——CI 无 latex 环境，故单测需走 mock subprocess 或保留环境 skip。不应为了单测引入对 latex 安装的依赖。

### 实施顺序约束

C2 提常量先行（机械抽取，零风险）；C1 抽函数按"`_build_compile_env` → `_diagnose_log`/`_format_compile_error` → `_run_xelatex`/`_run_xdvipdfmx`"顺序，每一步保持端到端测试可跑。