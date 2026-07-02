# Issue 019：提取共享图片复制工具 `shared/image_utils.py`

## Parent

ADR-0011（学科代码重复消除与共享层提取）— 图片复制逻辑重复

## What to build

将项目中 13 份独立的图片复制逻辑统一为一个共享函数 `copy_md_images()`，消除重复。

**当前问题**：
- 7 个 `subject.py` 的 `_write_problems_to_dirs` 中各有 1 份逐字相同的 `_copy_img` 内联函数
- `core/defaults.py` 中有 3 份独立的 `find_img` + `img_pat.sub(repl, ...)` 实现（`default_split_lecture`、`default_split_exam`、`default_generate_knowledge`）
- `shared/` 中另有 3 份独立的图片复制逻辑

所有 13 份代码实现相同的核心逻辑：遍历 Markdown 中的 `![...](...)` 图片引用，从源目录查找图片文件，复制到目标目录，重写路径。

**修复方向**：
```python
# shared/image_utils.py
def copy_md_images(
    md_content: str,
    src_media_dir: Path,
    target_img_dir: Path,
) -> str:
    """复制 Markdown 内容中引用的所有图片到目标目录，返回重写路径后的内容。"""
```

## Acceptance criteria

- [ ] `shared/image_utils.py` 提供 `copy_md_images()` 函数，参数清晰
- [ ] 7 个 `subject.py` 的 `_write_problems_to_dirs` 改为调用该函数，删除内联 `_copy_img`
- [ ] `core/defaults.py` 的 3 处图片复制改为调用该函数（或合理的薄封装）
- [ ] 现有所有拆分流程端到端通过，图片路径正确、文件落盘正确
- [ ] 新增单元测试覆盖：本地图片复制、HTTP 图片跳过、无图片内容不变

## Blocked by

None — 可立即开始
