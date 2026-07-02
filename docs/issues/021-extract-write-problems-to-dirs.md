# Issue 021：`_write_problems_to_dirs` 提取到基类

## Parent

ADR-0011（学科代码重复消除与共享层提取）— `_write_problems_to_dirs` 重复

## What to build

将 7 个学科中 ~62 行的 `_write_problems_to_dirs` 方法提取到 `core/base_subject.py` 基类。这是项目中最大的单一重复源（约 434 行）。

**差异点**：7 个学科中仅高中历史的 `_clean.md` 生成有差异——它保留粗体文本内容（`\1`），而其他 6 科替换为控制字符（`\x01`）。

**修复方向**：
- 基类实现完整方法，使用 Issue 019 的 `copy_md_images()` 替代内联 `_copy_img`
- bold 替换策略通过类属性 `_clean_bold_replacement: str = "\x01"` 注入
- 高中历史覆盖为 `"\1"`
- 各 `subject.py` 删除该方法，零代码残留

## Acceptance criteria

- [ ] 基类实现 `_write_problems_to_dirs`，行为与当前 7 份拷贝完全一致
- [ ] 使用 `shared/image_utils.py` 的 `copy_md_images()` 替代内联图片复制
- [ ] 高中历史的粗体保留行为通过 `_clean_bold_replacement = "\1"` 保持
- [ ] 所有 7 个学科的拆分流程端到端通过：`第N题.md`、`_clean.md`、图片落盘正确
- [ ] 新增单元测试：`_write_problems_to_dirs` 的图片复制、_clean.md 生成、边界情况

## Blocked by

Issue 020（`core/base_subject.py` 基类框架）
