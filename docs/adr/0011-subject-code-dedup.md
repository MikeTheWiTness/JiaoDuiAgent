# ADR 0011：学科代码重复消除与共享层提取

**状态**：已接受（Issue 019-024 待实施）
**日期**：2026-06-30
**更新日期**：2026-07-02
**决策者**：MikeTheWiTness
**关联**：[[ADR 0010 Harness/ReAct/Plan Mode 升级]](0010-harness-react-planmode-upgrade.md)
**GitHub Issues**：[#47](https://github.com/MikeTheWiTness/JiaoDuiAgent/issues/47) [#48](https://github.com/MikeTheWiTness/JiaoDuiAgent/issues/48) [#49](https://github.com/MikeTheWiTness/JiaoDuiAgent/issues/49) [#50](https://github.com/MikeTheWiTness/JiaoDuiAgent/issues/50) [#51](https://github.com/MikeTheWiTness/JiaoDuiAgent/issues/51) [#52](https://github.com/MikeTheWiTness/JiaoDuiAgent/issues/52)

---

## 背景

ADR-0010 的 grill 过程中，对 6 个学科的 `subject.py`、`config.json`、`app.py`、`main.py`，以及共享层的切割方法和校对模式做了全面重复度分析。以下是发现，待单独重构时执行。

**约束**：各学科保持独立，不做跨学科的基类强制统一（部分学科开发未完成，区分度还未拉开）。

---

## 发现

### 一、subject.py 层（6 科 × ~250 行）

| 方法 | 重复度 | 说明 |
|------|--------|------|
| `_write_problems_to_dirs()` | 100% | 6 份逐字拷贝 |
| `get_ui_features()` | 100% | 6 份逐字拷贝 |
| `generate_knowledge()` | 100% | 6 份同调用 |
| `collect_paper_dirs()` | 100% | 6 份同调用 |
| `get_question_prompt()` | 95% | 结构相同，仅 config 键名不同 |
| `get_knowledge_prompt()` | 95% | 同上 |
| `get_review_prompt()` | 90% | 同上 |
| `proofread_one()` | 85% | 仅 pre_hook 有无差异 |

### 二、app.py / main.py 层

| 文件 | 重复度 | 说明 |
|------|--------|------|
| `app.py` | 99% | 物理/语文 163字节，其他 ~384字节（仅注释差异） |
| `main.py` | 90% | 4 科完全同(910字节)，小学数学多了 PyInstaller 路径处理 |

### 三、config.json 内重复

`question_prompt_lines` 和 `knowledge_prompt_lines` 中的格式规则段落（标记格式规则、配图错误标记方式、修改原因规则）是两个 prompt 之间的逐字拷贝。

### 四、切割方式的图片复制逻辑

`default_split_lecture`、`default_split_exam`、以及 6 个学科的 `_write_problems_to_dirs` 中各自包含一份相同的图片复制逻辑（`find_img` → `shutil.copy2` → `re.sub`）。

**总计算**：8 份相同的图片复制代码。

### 五、校对模式分支

`_conversion_thread` 中"批注评审"和"试卷"模式的差异仅 13 行代码（占位符注入 + 批注提取），其余流程完全相同。

---

## 待决策项

以下在重构时逐项决策：

1. subject.py 基类提取范围（全方法 or 仅高重复度方法）
2. config.json 格式规则复用机制（模板引用 or 运行时拼接）
3. 图片复制逻辑统一为 `shared/image_utils.py`
4. 批注评审合并为"试卷 + hook"模式
5. app.py/main.py 统一入口
