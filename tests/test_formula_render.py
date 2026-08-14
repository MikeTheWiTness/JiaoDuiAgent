"""shared/formula_render.py 单元测试

锁定 latex_to_png 的渲染成功/降级边界（CJK 拒绝、异常降级、空串）。
"""
import tempfile
import unittest
from pathlib import Path

try:
    import matplotlib
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from shared.formula_render import _CJK_FONT, latex_to_png


@unittest.skipUnless(HAS_MPL, "matplotlib 不可用，跳过公式渲染测试")
class TestLatexToPng(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_formula_render_test_")
        self.out = Path(self.tmp) / "f.png"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_simple_formula_renders(self):
        self.assertTrue(latex_to_png(r"v = at", self.out))
        self.assertTrue(self.out.exists())
        with open(self.out, "rb") as f:
            self.assertTrue(f.read(8).startswith(b"\x89PNG"))

    def test_frac_and_greek_renders(self):
        self.assertTrue(latex_to_png(r"E = n\frac{\Delta\Phi}{\Delta t}", self.out))

    def test_mathrm_with_space_renders(self):
        self.assertTrue(latex_to_png(r"\mathrm {B}", self.out))

    def test_chinese_renders_with_cjk_font_or_rejects(self):
        """有系统 CJK 字体时中文公式渲染成功；无字体时拒绝。"""
        ok = latex_to_png(r"Q_{电热}", self.out)
        if _CJK_FONT:
            self.assertTrue(ok)
            self.assertTrue(self.out.exists())
        else:
            self.assertFalse(ok)
            self.assertFalse(self.out.exists())

    def test_chinese_text_cmd_renders_with_cjk_font_or_rejects(self):
        ok = latex_to_png(r"\text{线圈}A", self.out)
        if _CJK_FONT:
            self.assertTrue(ok)
        else:
            self.assertFalse(ok)

    def test_matrix_rejected(self):
        self.assertFalse(latex_to_png(r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}", self.out))
        self.assertFalse(self.out.exists())

    def test_empty_rejected(self):
        self.assertFalse(latex_to_png("", self.out))
        self.assertFalse(latex_to_png("   ", self.out))

    def test_failed_render_leaves_no_file(self):
        # 渲染失败后不应残留上次成功的文件
        self.assertTrue(latex_to_png(r"v=at", self.out))
        self.assertFalse(latex_to_png(r"\begin{cases} a & b \end{cases}", self.out))
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
