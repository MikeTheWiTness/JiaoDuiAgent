# ADR 0023：物理/化学跨模块凭证设置逻辑去重 + 缓存锁 + env 持久化保键

**状态**：已接受（待落地，独立支线）
**日期**：2026-07-23（2026-07-24 修订：回退 C1 方案为纯去重，不动第三轨跨模块传递时序）
**决策者**：MikeTheWiTness
**关联**：[[ADR 0019 架构审查修复]](0019-architecture-review-fixes.md)、[[ADR 0006 物理 ReAct 学科化]](0006-physics-react-subject-specialization.md)

---

## 背景

API 凭证当前有**三条传递通道**：

1. **轨 1 `.env` → `load_env_config`**（`core/env_config.py`）：只识别三键 `API_URL/API_KEY/MODEL_NAME`，其余静默丢弃。`save_env_config` 直接覆写文件，抹掉用户手写的额外键与注释。
2. **轨 2 `SessionContext`**（`core/session_context.py`）：运行时注入，UI / format_enforcement / smart_split 三处都经它。
3. **轨 3 `set_*_api_config`**（`shared/physics_tools.py:23-39`、`shared/chemistry_tools.py:70-86`）：`defaults.py:832-838` 把 ctx 凭证**晚绑定**到两个学科内嵌工具模块的 `threading.local()` 私有存储。ADR-0019 C2 已把 `_api_config` 改为 `threading.local()` 解决并发竞态。

**第三轨为什么存在（关键）**：`core/base_subject.py:38` `__init__` 内 `self.tools = self.build_tools()`——SubjectApp 构造期即无参实例化 tools，此刻 `SessionContext` 还不存在。ctx 一直要到 `_proofread_thread`（`core/defaults.py:832-838` 的 `set_*_api_config(ctx...)`）才构造出 url/key/model/output_dir。这条晚绑定链是第三轨 threading.local 的存在理由。

两个顺带问题：
- **`from_credentials` 默认值不符**：`SessionContext` dataclass 默认 `max_loops=20`，但 `from_credentials` 工厂默认 `3`——两入口差 6.7 倍。三个调用点（`format_enforcement:134` 传 3、`smart_split:97` 传 1、UI 传学科配置）无一依赖默认值。
- **`config_loader._config_cache` 无锁**：模块级全局可变 dict，UI 批量校对下有竞态；目录被移动 / `.env` 修改后 cache 不失效，只能手动 `clear_config_cache()`。

## 决策

### 范围原则

**本 ADR 是纯优化，不改任何功能与运转时序。** 凭证三轨的存在与传递链保持现状——第三轨跨模块 threading.local 不删除、`build_tools` 的无参实例化不动、`defaults.py:832-838` 的晚绑定调用保留、`langchain_core.tools.BaseTool` 子类的构造签名不变。本 ADR 只解决三件可独立验证的纯优化事：去重、加锁、保键。

### C1：物理/化学跨模块凭证设置逻辑去重（不删第三轨）

`shared/physics_tools.py:23-39` 与 `shared/chemistry_tools.py:70-86` 的 `_api_config: threading.local()` + `set_*_api_config(...)` + `_get_api_config()` 三段函数体几乎逐行复制。本 ADR 抽到 `shared/_subject_api_config.py`（新模块）单一实现：

```python
# shared/_subject_api_config.py
import threading

_local = threading.local()

def set_subject_api_config(api_url, api_key, model, output_dir=None):
    _local.value = {"api_url": api_url, "api_key": api_key,
                    "model": model, "output_dir": output_dir}

def get_subject_api_config() -> dict:
    return getattr(_local, "value", {})
```

`physics_tools.py` / `chemistry_tools.py` 改为：

```python
from shared._subject_api_config import set_subject_api_config, get_subject_api_config

# 保留旧函数名作薄包装，签名与参数顺序逐字一致
def set_physics_api_config(api_url, api_key, model, output_dir=None):
    set_subject_api_config(api_url, api_key, model, output_dir)

def _get_api_config():
    return get_subject_api_config()
```

**严格保留项**：
- `defaults.py:832-838` 的 `set_physics_api_config(ctx...)` / `set_chemistry_api_config(...)` 调用不动。
- `ChemistryIndependentSolveTool` / `IndependentSolveTool` 的 `__init__` 不动；继续 `Tool()` 无参实例化；继续从 `_get_api_config()` 读凭证。
- `build_tools()` 的调用时机不动。
- 函数签名、参数顺序、`output_dir=None` 默认值、`threading.local()` 存储方式——**逐字保持原样**。
- 运行时调用序列、并发安全保证、晚绑定时机**完全不变**。

### C2：`from_credentials` 默认值与 dataclass 对齐

`from_credentials` 的 `max_loops` 默认值改为 `20`，与 dataclass 默认一致。三个调用点（format/split/UI）现全部显式传值——对齐后**对现有调用零影响**（无一依赖默认值）。dataclass 默认值成为唯一"未传值"真源。

`from_credentials` 工厂本身保留——三个调用点仍明示传值，其语义清晰、文档自明。

### C3：config_loader 缓存加锁 + mtime 校验

`core/config_loader.py`：
- 加 `threading.Lock` 全包 `load_config` 的读写。
- `_config_cache` 的 key 从 `subject_dir` 升级为 `(subject_dir, mtime_tuple)`——盘查 `config.json` 与 `.env` 的 mtime；任一变更则 cache 自动失效。
- 现有 `clear_config_cache()` 保留，用于强制刷新。
- **行为不变保证**：cache 命中时返回的 dict 与现状一致；未命中时的解析路径与现状一致。加锁与 mtime 仅改变"何时复用 / 何时失效"的决策，不影响"返回什么"。

### C4：env_config 读改写保留额外键

`core/env_config.py:save_env_config`：
- 从"覆写三键"改为"读入现存的 `.env`、仅替换 `API_URL/API_KEY/MODEL_NAME` 三个键、保留其他键与注释、写回"。
- 读入时用 `string.split('=', 1)` 保留值里的 `=`（如 base64 key）——`load_env_config:18` 已是这样，`save_env_config` 是覆写模式没继承。
- 已存在的无法识别键保留原样写回，注释行保留。
- **行为变更边界**：当 `.env` 原本只有规范三键、无额外键、无注释——本 ADR 写出的文件与原"覆写三键"生成的文件**逐字相同**。差异仅在原 `.env` 含额外键或注释时：原代码会抹掉它们，本 ADR 保留它们。这是**用户在 GUI 里点"保存配置"时的行为变更**（修 bug 而非新增功能——原行为是数据丢失），属本 ADR 接受的小幅安全收益，**但需在 review 时明确这是数据保全型修复**。若要严格"零变更"，可选保留覆写行为；本 ADR 选读改写作为正确性修复。
- `load_env_config` 不动——它本就只返回三键 dict，无需扩。

## 明确不做（本支线范围外）

- **删除第三轨跨模块 threading.local**：晚绑定时序不动。原方案"工具接 ctx 作为构造参数"会强制重写 `BaseSubjectApp.__init__` 与 7 学科 `build_tools()` 调用时机——那不是优化，是状态/时序重构。已从本 ADR 剔除（2026-07-24 审查发现）。
- **`build_tools()` 时机变更**：现状 `__init__` 期调用，不动。
- **`langchain_core.tools.BaseTool` 构造签名改写**：BaseTool 是 pydantic model，私加构造参数会踩字段约束。不动。
- **`.env` 迁到 python-dotenv**：引入新依赖；现 `load_env_config` 够用。
- **`SessionContext` 字段变更**：不动。
- **多学科 `.env` 合并到主仓**：每学科独立 `.env` 是历史与隔离需求，不动。

## 影响

### 正面
- physics/chemistry 两文件跨模块设置代码去重（单一源），未来再加工具不再各自抄一份
- 缓存并发安全 + 自动失效
- env 持久化保留用户手写注释与额外键（数据保全型修复）

### 负面 / 风险
- **薄包装 `set_physics_api_config` / `set_chemistry_api_config` 仍保留**：未完全消除旧名字，存在两份薄包装。代价可接受——保留既有 API 表面比对所有调用方做 grep 修改（与本 ADR"不改功能"原则一致）。
- **C4 对"用户在 GUI 保存配置"是行为变更**：从"抹掉额外键/注释"改为"保留"。此变更属正确性修复而非新增功能；落地时若 review 团队认为应完全零变更，可回退 C4。
- **`config_loader` mtime 校验增加一次 stat**：开销小，可接受；且 cache 命中行为与现状完全一致。

### 实施顺序约束
C4（env_config 读改写）可先行——与 C1/C2/C3 解耦。C1 跨模块去重保留薄包装后，调用方零改动。C3 缓存锁+mtime 独立可验证。三者无强依赖。