"""shared/decor_utils.py 单元测试

锁定装饰图片清除的尺寸阈值（0.4in）与 alt 匹配规则，
回归案例来自实测数据（2026-08-11 物理讲义第 1 讲 + 电路改）。
"""
import pytest

from shared.decor_utils import (
    DECOR_MAX_H,
    DECOR_MAX_W,
    strip_decor_images,
    strip_decor_images_from_file,
)


class TestStripDecorImages:
    """验证 strip_decor_images 核心行为。"""

    def test_threshold_is_04_inch(self):
        """阈值常量应为 0.4in（实测装饰图标 0.194in、真实图最小 0.479in）。"""
        assert DECOR_MAX_W == 0.4
        assert DECOR_MAX_H == 0.4

    def test_title_icon_test_alt_deleted(self):
        """标题行 test 图标（0.194×0.194in）应被删除。"""
        md = "### 模型大招![test](media/image1.png){width=\"0.194in\" height=\"0.194in\"}"
        assert strip_decor_images(md) == "### 模型大招"

    def test_title_icon_empty_alt_deleted(self):
        """空 alt 的小图标同样应被删除。"""
        md = "### 必备知识![](media/image17.png){width=\"0.194in\" height=\"0.194in\"}"
        assert strip_decor_images(md) == "### 必备知识"

    def test_problem_image_kept(self):
        """真实题目图（image16 回归案例：0.875×0.781in、alt=test）应保留。"""
        md = "![test](media/image16.png){width=\"0.875in\" height=\"0.78125in\"}"
        assert strip_decor_images(md) == md

    def test_smallest_real_image_kept(self):
        """实测最小真实题目图（image81：0.479×0.667in）应保留。"""
        md = "![test](media/image81.png){width=\"0.479in\" height=\"0.667in\"}"
        assert strip_decor_images(md) == md

    def test_stretched_table_icon_kept(self):
        """表格内被拉伸的同款图标（1.222×1.472in）接受漏删，应保留。"""
        md = "![test](media/image2.png){width=\"1.222in\" height=\"1.472in\"}"
        assert strip_decor_images(md) == md

    def test_boundary_exact_04_kept(self):
        """恰好 0.4in 应保留（规则是严格小于）。"""
        md = "![test](media/x.png){width=\"0.4in\" height=\"0.4in\"}"
        assert strip_decor_images(md) == md

    def test_boundary_just_below_deleted(self):
        """0.399in 已低于阈值，应删除。"""
        md = "![test](media/x.png){width=\"0.399in\" height=\"0.399in\"}"
        assert strip_decor_images(md) == ""

    def test_old_threshold_size_kept(self):
        """旧阈值边界（1.3×1.5in）的图在新规则下更应保留。"""
        md = "![test](media/y.png){width=\"1.3in\" height=\"1.5in\"}"
        assert strip_decor_images(md) == md

    def test_large_image_kept(self):
        """大图（2.1875×1.865in）应保留。"""
        md = "![test](media/image34.jpg){width=\"2.1875in\" height=\"1.8645833333333333in\"}"
        assert strip_decor_images(md) == md

    def test_width_only_not_matched(self):
        """只有 width 无 height 的图片引用不匹配正则，应原样保留。"""
        md = "![test](media/x.png){width=\"0.194in\"}"
        assert strip_decor_images(md) == md

    def test_non_test_alt_kept(self):
        """alt 为其他文本（如 IMG_256、uuid）的图不匹配正则，应保留。"""
        md = "![IMG_256](media/image256.png){width=\"0.208in\" height=\"0.146in\"}"
        assert strip_decor_images(md) == md

    def test_mixed_content(self):
        """混合场景：标题图标删、题目图留、其他 alt 留。"""
        md = (
            "### 模型大招![test](media/i1.png){width=\"0.194in\" height=\"0.194in\"}\n"
            "![test](media/i16.png){width=\"0.875in\" height=\"0.78125in\"}\n"
            "![IMG_1](media/i3.png){width=\"0.2in\" height=\"0.2in\"}"
        )
        assert strip_decor_images(md) == (
            "### 模型大招\n"
            "![test](media/i16.png){width=\"0.875in\" height=\"0.78125in\"}\n"
            "![IMG_1](media/i3.png){width=\"0.2in\" height=\"0.2in\"}"
        )


class TestStripDecorImagesFromFile:
    """验证 strip_decor_images_from_file 文件写回行为。"""

    def test_file_modified_when_decor_found(self, tmp_path):
        """文件含装饰图标时应写回清理后的内容并返回 True。"""
        f = tmp_path / "doc.md"
        f.write_text("### 必备知识![test](media/i.png){width=\"0.194in\" height=\"0.194in\"}", encoding="utf-8")
        assert strip_decor_images_from_file(str(f)) is True
        assert f.read_text(encoding="utf-8") == "### 必备知识"

    def test_file_untouched_when_no_decor(self, tmp_path):
        """文件无装饰图标时不应写回，返回 False。"""
        f = tmp_path / "doc.md"
        original = "![test](media/i16.png){width=\"0.875in\" height=\"0.78125in\"}"
        f.write_text(original, encoding="utf-8")
        assert strip_decor_images_from_file(str(f)) is False
        assert f.read_text(encoding="utf-8") == original
