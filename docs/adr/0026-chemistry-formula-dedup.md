# ADR 0026：化学式解析双源同步测试锁（运行时保留字面量）

**状态**：已接受（待落地，独立支线）
**日期**：2026-07-23（2026-07-24 修订：回退主方案为字面量保留 + CI 同步锁；inspect.getsource runtime 注入方案被否决，因 PyInstaller 打包后 OSError 推翻）
**决策者**：MikeTheWiTness
**关联**：[[ADR 0019 架构审查修复]](0019-architecture-review-fixes.md)

---

## 背景

`shared/chemistry_tools.py:parse_chemical_formula`（24-65）与 `shared/sympy_tools/templates.py:189-223` 沙箱模板内嵌的 `_parse_formula` 是**两份逐字相同** 的化学式解析算法，仅变量名前缀不同。`chemistry_tools.py:22-30` 注释明确写"两端须保持同步"。任一侧修 bug 都需手动同步另一侧——审查 P1 的"DRY 被注释承诺维系"问题。

两份隔离的理由：`parse_chemical_formula` 在主进程作为普通 Python 函数被调用；`_parse_formula` 是字符串源码内嵌到 `templates.py:chemistry_balance` 模板里，组合后送 `shared/sympy_tools/sandbox.py` 在隔离子进程中执行，或打包模式下进程内 exec。沙箱是受限命名空间，不能 `from shared.chemistry_tools import parse_chemical_formula`。

## 主方案（runtime inspect.getsource 注入）的否决理由

原主方案"用 `inspect.getsource(parse_chemical_formula)` 在 templates.py 模块加载期生成 `_PARSE_FORMULA_SRC` 注入沙箱"——2026-07-24 审查发现致命风险：

- `templates.py` 的 `_TEMPLATES` dict 在模板模块 `import` 时即构造，而 import 发生在**应用启动早期**。
- PyInstaller 打包后字节码没有源码，`inspect.getsource` 在打包运行时抛 `OSError: could not get source code`。
- 此 OSError 会**让整个主应用无法启动**（不是单条功能降级）。
- 原主方案提的"构建脚本生成 `_generated_formula_src.py` 字面量"虽能绕 OSError，但把"一份源"重组成"主源 + 构建产物字面量"两份；构建链路若遗漏生成步骤，打包启动崩。**为一个原本能工作的功能引入新的运行时风险**，违反"纯优化不改功能"原则。

## 决策

### C1：运行时保留字面量；新增 CI 同步测试锁

**运行时行为不变**——`templates.py:chemistry_balance` 模板里的 `_parse_formula` 仍以字面字符串源码内嵌，与现状逐字一致。

**新增测试锁 `tests/test_chem_formula_sync.py`（开发模式跑）**：
- 在开发模式（有源码）下，用 `inspect.getsource(parse_chemical_formula)` 取主源函数体源码。
- 从 `templates.py._TEMPLATES["chemistry_balance"].template` 字符串里提取内嵌的 `_parse_formula` 源码块。
- 对两者做**规范化对比**：去掉前后空白、规范缩进、统一命名（`parse_chemical_formula` ↔ `_parse_formula` 互换），断言结构逐字一致。
- 任一侧修改后忘同步另一侧，CI（本地）即报红。

**注意**：此测试锁仅在**开发模式**下能取 `inspect.getsource`；CI 安装了源码，正常跑。

**仍是两份手抄同步**——本 ADR 不消除双份，只加保险绳。代价：同步靠人手动，CI 仅反映漂移。收益：零运行时风险、零功能变更。

### C2：`_MOLAR_MASSES` 大字典一并未入

`shared/sympy_tools/tools.py:362-388` 的 `_MOLAR_MASSES` 大字典与 `templates.py` 的 `stoichiometry` 模板通过 `molar_masses` 参数耦合。审查 P2 M10 指出该字典应外置。本 ADR 处理：

将 `_MOLAR_MASSES` 抽到 `shared/chemistry_tools.py` 模块级常量（物理化学专题所在），`tools.py` 与 `templates.py` 都从那里 import。**单一真源、便于扩展**。**行为不变约束**：常量值的元素集合、各元素质量逐字保持与现 `tools.py:362-388` 一致。

对于 `stoichiometry` 模板通过 `molar_masses` 参数注入的情况，统一改 import 后，参数注入路径与运行时行为不变。

## 明确不做（本支线范围外）

- **沙箱机制重构**：subprocess vs 进程内 exec 双模式是历史决策，不动。
- **`inspect.getsource` runtime 注入**：被本 ADR 否决（PyInstaller OSError 推翻）。若未来想彻底消除双份，路径是"构建时生成字面量打包"，但本支线不做。
- **`build_code`(304-491 ~190 行单函数) dispatch 拆分**（审查 P2 L7）：与化学去重正交，留给日后小补丁。
- **`json_repr` 的 `Template` 转义陷阱改 `str.Formatter`**（审查 P2 L6）：独立小改动。

## 影响

### 正面
- CI 同步锁防止手抄漂移——单边修改忘同步另一侧立即报红
- `_MOLAR_MASSES` 单一真源，扩展元素质量只改一处
- 运行时零风险（与现状完全一致）

### 负面 / 风险
- **仍是两份手抄同步**：CI 仅揭露漂移，不自动同步——漂移仍需人手修。代价可接受：同步测试锁已经在审查前的危险期发生过（手抄同步间差了变量名），CI 报红即保护未来不再漂。
- **CI 测试锁依赖开发模式有源码**：打包后的应用运行环境不在覆盖范围（打包应用不跑测试）。可接受——测试锁是开发期保护。
- **`_MOLAR_MASSES` 抽到 `chemistry_tools.py` 后**，`tools.py` 不再持有字典字面量——若有调用方直接从 `sympy_tools/tools.py` 导入 `_MOLAR_MASSES`，需改为从 `chemistry_tools` 导入。全仓 grep `_MOLAR_MASSES` 顺手清零。

### 实施顺序约束
C2 抽 `_MOLAR_MASSES` 先行（独立、低风险，全仓 grep 后单点改造）。C1 同步测试锁随后——测试需引用 templates.py 已经稳定的字面量（不能边改 C2 边写测试）。