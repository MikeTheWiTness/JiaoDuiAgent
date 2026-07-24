# ADR 0019：架构审查修复 —— 沉默故障 + ADR 残留拆除 + 测试防线复位

**状态**：已落地（部分）— 主体经 commit `a0309df`（"feat: ADR-0019 架构审查修复"）合并；C1.3 的 except 全扫有 6 处未覆盖，延后到 [[ADR 0021]](0021-call-api-refactor-bashtool-safety-test-degradation.md) 承接
**日期**：2026-07-22
**决策者**：MikeTheWiTness
**关联**：[[ADR 0012 框架工程债]](0012-framework-engineering-debt.md)、[[ADR 0015 统一校对流程]](0015-unified-proofread-flow.md)、[[ADR 0016 工具生成校对标记]](0016-tool-generated-proofread-marks.md)、[[ADR 0017 统一规则拆分]](0017-unified-section-split.md)、[[ADR 0018 智能拆分工具化]](0018-smart-split-tool-integration.md)、[[ADR 0021 call_api 重构 + BashTool 安全 + 退化测试]](0021-call-api-refactor-bashtool-safety-test-degradation.md)

---

## 背景

2026-07-22 全面架构审查（3 个并行侦察代理 + 测试套件实测：593 通过 / 20 失败）发现：

1. **沉默故障**：ADR-0012 将 `call_api` 改为 `ctx` 签名后，`format_enforcement._bash_format_fix`、`smart_split`、`knowledge_split` 三处调用方未迁移，必抛 TypeError 并被 `except Exception` 吞掉——「LLM 格式修正」与「智能分割」两个功能实际从未工作，用户无感知。
2. **并发状态泄漏**（🔴2/3/5 同根因）：每单元运行状态（output_dir、max_loops、求解工具配置）存放在跨线程共享位置——`_API对话记录.md` 多线程互覆、`ctx.max_loops=0` 污染后续单元、物理/化学全局 `_api_config` 竞态写错目录。
3. **ADR-0017/0018 落地一半**：「知识提取」概念已废弃但仍以必填字段 + 7 份实现 + UI 状态的僵尸形态存在；`_is_unit_dir` 不识别 `单元N/`；manual 拆分不认新标记；决策 9 的 `.skip_proofread` 协议三处断链。
4. **测试信号失效**：20 个红灯常态化（13 陈旧 + 7 机器绑定）；2 处仿冒测试（拷贝实现进测试文件再断言）；`parsing.py`、`format_enforcement`、`.skip_proofread` 协议等高危路径零覆盖。

---

## 决策

### C1：修复 call_api 断链调用

1. **删除 `shared/knowledge_split.py`（576 行死模块）及其测试**。知识概念已被 ADR-0017 废弃，该模块生产零调用，且其知识切割理念与 section 模式冲突。
2. **`SessionContext` 加工厂方法**（`from_credentials(api_url, api_key, model, output_dir=...)`），`_bash_format_fix` 与 `smart_split` 经工厂构造 ctx 调用 `call_api`。ctx 构造知识只存在于一处。
3. **异常吞掉全扫**（~10 处）：所有 `except` 改为 `log()` 输出完整 traceback + 上下文摘要（函数名/输入摘要），落实 AGENTS.md 硬性要求。

   **C1.3.1（落地状态备忘）**：commit `a0309df` 落地了 `format_enforcement._bash_format_fix`、`smart_split`、`knowledge_split` 三条断链链路的 except 补完。剩余 6 处未扫——`api_client._save_conversation_log_full`（`except: pass`）、`parsing.save_proofread_json`、`base_subject._clean.md`、`chemistry_tools` API 失败、`chinese_classics_tools.extract_text_start_via_api`、`defaults.py`（清洗/出题意图清理）。2026-07-23 复审确认这 6 处原样未动。**承接**：`_save_conversation_log_full` 已并入 [[ADR 0021]](0021-call-api-refactor-bashtool-safety-test-degradation.md) C3 合并 save_log 时一并扫尾；其余 5 处回归本 ADR 的 C1.3 范畴继续承接修复，不另立新 ADR。

### C6：测试防线复位

4. **13 个陈旧测试逐个判断**：能代表当前行为的重写（`test_prompt_quality` 改断言单元标记、`test_math_v3_standalone` 适配 ADR-0017 后行为、`test_excerpt_extraction` 改测 n-gram 算法契约）；依赖本机数据目录的（`test_body_segment`×5、`test_math_pdf`×8）加环境 skip 守卫。
5. **2 处仿冒测试改 import 真实实现**（`test_default_proofread_one.py`、`test_chemistry_balance.py`）——AGENTS.md「禁止削弱测试」。
6. **红线机制：全绿 + 最小 GitHub Actions CI**（push/PR 跑 pytest）。无强制力的红线已被证明会退化。
7. **4 把回归锁**：`parsing.py` 落盘单测、`.skip_proofread` 跨层契约测试、`format_enforcement` 直接单测（C1 回归锁）、`_is_unit_dir` 识别测试（C3 回归锁）。

### C2：每单元状态收编

8. **每单元派生 ctx 副本**：校对 worker 入口 `dataclasses.replace(ctx, output_dir=q_dir)`；`interrupt_event` 引用复制，天然保持全局共享。**`SessionContext` 加 `frozen=True`**，把「不可变」从注释变成运行期约束（repo 内唯一改写点即本次要删的 843 行，frozen 安全）。
9. **删除 `defaults.py:843` 的 `ctx.max_loops = 0`**：`tools=[]` 时 payload 无 tools 字段，工具循环本就不会启动，该行是冗余保护且是污染源。
10. **physics/chemistry `_api_config` 改 `threading.local()`**：照抄 `bash_tool.py:213` 已有模式，setter/getter 签名不变。两文件的复制粘贴大重复留给后续 C4 阶段。

### C3：拆除 ADR-0017/0018 残留

11. **删除范围 = 核心僵尸链 + 周边明确死代码**：`default_generate_knowledge`、`get_knowledge_prompt` 抽象及 7 份实现、`base_subject.py:78` 旧签名、`_has_real_content`、`split_by_knowledge_markers` 及旧标记常量、UI 死 checkbox 与 `knowledge_prompt` 死状态、7 学科重复 `strip_decor_images` 调用；`config_loader_v2.py`、`paths.py`、`ModeSelector`、`ui_react.py`、`subject_react.py`、config_loader 死 getter、各学科未使用 import。外围半成品（`free_proofread`、`review_mode.is_review_mode`、`session.find_unfinished`、ADR-0016 helper 层）**保留**，由后续 C7 决策。
12. **`knowledge_prompt_lines` 直接彻底删除**：schema 移除该必填项 + 9 份 config.json 删除该字段（连同 `knowledge_agent_prompt_lines`）。**明确不留兼容层**——决策理由：config 全部在本仓库内受控，兼容层只会延长僵尸寿命。
13. **config 冗余顺手全清**：删除与 schema 默认值相同的字段（`split_mode`×9、`exam_pattern`×7、空 `section_pattern_extensions`×8）、死字段 `section_boundary`×8（其 getter 全仓零调用）、初中英语的哑弹 `section_pattern`。每份 config 只留真差异。
14. **修 🔴4/🔴6/🔴7**：`_is_unit_dir` 补「单元」识别；初中英语 `get_tool_instructions` 的 `tools` NameError；manual 拆分入口切到 `split_by_unit_markers`。
15. **ADR-0017 决策 9 接线**：高中历史 `remove_navigation_units` → `mark_navigation_units`（创建 `.skip_proofread` 替代删目录），配决策 7 的契约测试。
16. **删除孤儿学科目录** `subjects/初中物理v3.0`、`subjects/初中生物v3.0`（仅 config.json，无代码无引用）。

---

## 明确不做（本轮范围外）

- **🔴8 转换/拆分阶段中断盲区** → 留给 C5（校对编排从 UI 下沉 core）统一设计，不做零散修补。
- **C4 学科浅模块下沉、C5 UI 编排下沉** → 结构性投资，本轮 C1-C3 落地后单独立项。
- **C7 ADR-0016 半成品（完成或拆除）** → 单独的决策点，需确认工具标记路线是否仍是目标。
- **physics/chemistry 两文件的去重** → 归 C4。

---

## 影响

### 正面

- 复活「LLM 格式修正」「智能分割」两个宣称的功能
- 并发校对消除三类正确性风险（对话记录互覆 / max_loops 污染 / 求解文件写错目录）
- 删除 ~800 行死/半死代码 + 9 份 config 各减数十行死字段
- 测试套件恢复「全绿才可信」的信号价值，CI 提供强制力
- `SessionContext` frozen 化后，同类共享改写未来在运行期立即报错

### 负面 / 风险

- `knowledge_prompt_lines` 彻底删除无兼容层：若仓库外存在自建学科 config，启动校验会报缺字段——接受此风险（config 全部仓库内受控）
- 删除清单涉及面广，需测试套件全绿作为安全网（C6 先行）

### 实施顺序约束

**C6（测试复位）先行或与 C1 同步**——C1/C3 的修复必须落在全绿的安全网上；C1 的 format_enforcement 回归锁与 C3 的 `_is_unit_dir` 回归锁随各自修复一同交付。
