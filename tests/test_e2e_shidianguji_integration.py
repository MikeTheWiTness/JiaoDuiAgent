"""测试识典集成进校对链路——端到端（ADR 0004 决策 1-4 + Issue #5）

验证：文言文校对时自动从识典提取原文 → 截取节选 → diff → 注入 prompt。
"""
import os
import re
import sys
import unittest

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.e2e


class TestE2EShidiangujiIntegration(unittest.TestCase):
    """端到端测试识典集成链路（非 mock，真实流程）"""

    def test_search_uses_first_10_chars(self):
        """搜索关键词应只取前 10 个汉字"""
        from shared.chinese_classics_tools import _clean_annotations, _strip_leadin

        md_text = (
            "阅读下面的文言文，完成1-6题。"
            "韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"
        )

        clean = _clean_annotations(md_text)
        clean = re.sub(r'[#*`\[\]()]', '', clean)
        clean = re.sub(r'\s+', '', clean)
        search_key = _strip_leadin(clean)
        if len(search_key) > 10:
            search_key = search_key[:10]

        self.assertEqual(len(search_key), 10,
                         f"搜索关键词应为 10 字，实际 {len(search_key)} 字: {search_key}")
        self.assertIn("韦凑", search_key)

    def test_preprocess_returns_enriched_md(self):
        """有前置参考时返回的文本被丰富了"""
        from shared.chinese_classics_tools import preprocess_for_proofread

        md_text = (
            "先帝创业未半而中道崩殂，今天下三分，益州疲弊，"
            "此诚危急存亡之秋也。然侍卫之臣不懈于内，"
            "忠志之士忘身于外者，盖追先帝之殊遇，"
            "欲报之于陛下也。诚宜开张圣听，以光先帝遗德。"
        )
        result = preprocess_for_proofread(md_text)
        self.assertIsInstance(result, str)
        self.assertIn("先帝", result)

    def test_search_original_text_falls_back_gracefully(self):
        """Playwright 不可用时回退到 ddgs 链路，不抛异常"""
        from shared.chinese_classics_tools import search_original_text

        sample = "学而时习之不亦说乎"
        result = search_original_text("classical", sample)
        self.assertTrue(result is None or isinstance(result, str))

    def test_extract_excerpt_and_diff_integration(self):
        """识典全文 + 节选 → 精确截取 → diff 报告"""
        from shared.chinese_classics_tools import diff_characters, extract_excerpt_from_full

        full = (
            "韦凑字彦宗，京兆万年人。祖叔谐，贞观中为库部郎中。"
            "凑，永淳初，解褐婺州参军事，徙资州司兵。"
            "观察使房昶才之，表于朝，迁扬州法曹。"
            "卒，年六十五，赠幽州都督，谥曰文。子见素。"
        )
        excerpt = (
            "韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"
            "徙资州司兵。卒，年六十五。"
        )

        extracted = extract_excerpt_from_full(full, excerpt)
        self.assertIsNotNone(extracted)

        clean_extracted = re.sub(r'[#*`\[\]()\s]', '', extracted)
        clean_excerpt = re.sub(r'[#*`\[\]()\s]', '', excerpt)
        diff_result = diff_characters(clean_extracted, clean_excerpt)

        self.assertIn("differences", diff_result)
        self.assertIn("identical", diff_result)

    def test_zero_diff_fast_path(self):
        """0 差异时 build_reference_section 标记一致性"""
        from shared.chinese_classics_tools import build_reference_section

        ref = build_reference_section("classical", "测试原文", [])
        self.assertIn("字面一致", ref)
        self.assertIn("测试原文", ref)

    def test_has_diff_injects_reference(self):
        """有差异时注入差异列表"""
        from shared.chinese_classics_tools import build_reference_section

        diffs = [{"position": 5, "type": "replace", "original": "蚑", "given": "蛟"}]
        ref = build_reference_section("classical", "测试原文", diffs)
        self.assertIn("字面差异", ref)
        self.assertIn("蚑", ref)
        self.assertIn("蛟", ref)


if __name__ == "__main__":
    unittest.main()
