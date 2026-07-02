# Issue 020：提取 `core/base_subject.py` 基类 — 零差异方法

## Parent

ADR-0011（学科代码重复消除与共享层提取）— subject.py 零差异方法提取

## What to build

新建 `core/base_subject.py`，放入 5 个在所有 7 个学科中完全一致（或仅类属性不同）的方法，各学科 `subject.py` 改为继承基类并删除重复代码。

**提取方法**：

| 方法 | 重复度 | 差异化方式 |
|------|--------|-----------|
| `generate_knowledge()` | 7/7 逐字相同 | 直接放基类 |
| `collect_paper_dirs()` | 7/7 逐字相同 | 直接放基类 |
| `post_proofread_hook()` | 7/7 空操作 | 基类默认空实现 |
| `get_ui_features()` | 7/7 仅 `show_knowledge_option` 不同 | `_show_knowledge_option: bool = True` 类属性 |
| `get_supported_file_types()` / `get_supported_extensions()` | 4 科完全一致 | 基类默认实现，需定制的学科覆盖 |

**重要**：基类放在 `core/` 而非 `subjects/`，避免学科目录间的兄弟依赖，不影响独立打包。

## Acceptance criteria

- [ ] `core/base_subject.py` 存在，包含 `BaseSubjectApp` 类
- [ ] 上述 5 个方法在基类中实现，各 `subject.py` 删除重复代码
- [ ] 高中历史的 `show_knowledge_option = False` 通过覆盖类属性实现
- [ ] 所有 7 个学科的校对、拆分、知识提取流程端到端通过
- [ ] 独立打包（PyInstaller）不受影响：每个学科的 `main.py` 仍可独立打包

## Blocked by

Issue 019（`shared/image_utils.py` 提取）
