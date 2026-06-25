import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.chinese_classics_tools import (
    detect_text_type,
    diff_characters,
    build_reference_section,
    search_original_text,
    preprocess_for_proofread,
)


class TestDetectTextType(unittest.TestCase):
    def test_classical_chinese_detected(self):
        text = """
        先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。
        然侍卫之臣不懈于内，忠志之士忘身于外者，盖追先帝之殊遇，欲报之于陛下也。
        诚宜开张圣听，以光先帝遗德，恢弘志士之气，不宜妄自菲薄，引喻失义，以塞忠谏之路也。
        """
        result = detect_text_type(text)
        self.assertEqual(result, "classical")

    def test_poetry_detected(self):
        text = """
        床前明月光，疑是地上霜。
        举头望明月，低头思故乡。
        """
        result = detect_text_type(text)
        self.assertEqual(result, "poetry")

    def test_modern_text_detected(self):
        text = """
        现代文阅读是语文考试中的重要题型。这篇文章主要讲述了作者对童年生活的回忆，
        通过细腻的描写展现了人物的性格特点。请回答以下问题：
        1. 文章的主旨是什么？
        2. 作者使用了哪些修辞手法？
        """
        result = detect_text_type(text)
        self.assertEqual(result, "modern")

    def test_classical_with_zhihuzi(self):
        text = "学而时习之，不亦说乎？有朋自远方来，不亦乐乎？"
        result = detect_text_type(text)
        self.assertEqual(result, "classical")

    def test_poetry_with_regular_lines(self):
        text = "春眠不觉晓，处处闻啼鸟。夜来风雨声，花落知多少。"
        result = detect_text_type(text)
        self.assertEqual(result, "poetry")


class TestDiffCharacters(unittest.TestCase):
    def test_identical_texts(self):
        original = "床前明月光"
        given = "床前明月光"
        result = diff_characters(original, given)
        self.assertEqual(len(result["differences"]), 0)
        self.assertTrue(result["identical"])

    def test_single_char_diff(self):
        original = "床前明月光"
        given = "床前名月光"
        result = diff_characters(original, given)
        self.assertGreaterEqual(len(result["differences"]), 1)
        self.assertFalse(result["identical"])

    def test_multiple_diffs(self):
        original = "学而时习之，不亦说乎"
        given = "学而时习之，不亦乐乎"
        result = diff_characters(original, given)
        diffs = result["differences"]
        self.assertGreaterEqual(len(diffs), 1)

    def test_extra_chars_in_given(self):
        original = "床前明月光"
        given = "床前明月光光"
        result = diff_characters(original, given)
        self.assertGreaterEqual(len(result["differences"]), 1)

    def test_missing_chars_in_given(self):
        original = "床前明月光"
        given = "床前明月"
        result = diff_characters(original, given)
        self.assertGreaterEqual(len(result["differences"]), 1)

    def test_diff_includes_position_info(self):
        original = "abcde"
        given = "abXde"
        result = diff_characters(original, given)
        self.assertTrue(len(result["differences"]) > 0)
        diff = result["differences"][0]
        self.assertIn("original", diff)
        self.assertIn("given", diff)


class TestBuildReferenceSection(unittest.TestCase):
    def test_classical_reference_section(self):
        original = "先帝创业未半而中道崩殂"
        diffs = [{"original": "创", "given": "篡", "position": 2}]
        result = build_reference_section("classical", original, diffs)
        self.assertIn("文言文", result)
        self.assertIn("原文", result)
        self.assertIn("差异", result)

    def test_poetry_reference_section(self):
        original = "床前明月光"
        diffs = [{"original": "明", "given": "名", "position": 2}]
        result = build_reference_section("poetry", original, diffs)
        self.assertIn("诗歌", result)
        self.assertIn("原文", result)

    def test_no_diffs_reference_section(self):
        original = "床前明月光"
        diffs = []
        result = build_reference_section("poetry", original, diffs)
        self.assertIn("原文", result)
        self.assertIn("一致", result)


class TestSearchOriginalText(unittest.TestCase):
    def test_modern_text_returns_none(self):
        result = search_original_text("modern", "这是现代文")
        self.assertIsNone(result)

    def test_empty_sample_returns_none(self):
        result = search_original_text("classical", "")
        self.assertIsNone(result)

    def test_function_exists(self):
        self.assertTrue(callable(search_original_text))


class TestPreprocessForProofread(unittest.TestCase):
    def test_modern_text_unchanged(self):
        text = "现代文内容"
        result = preprocess_for_proofread(text)
        self.assertEqual(result, text)

    def test_returns_string(self):
        text = "床前明月光"
        result = preprocess_for_proofread(text)
        self.assertIsInstance(result, str)

    def test_classical_text_has_reference_section(self):
        import shared.chinese_classics_tools as mod
        orig_search = mod.search_original_text

        def fake_search(text_type, sample):
            return "床前明月光，疑是地上霜。举头望明月，低头思故乡。"

        mod.search_original_text = fake_search
        try:
            text = "床前明月光，疑是地上霜。举头望明月，低头思故乡。"
            result = preprocess_for_proofread(text)
            self.assertIn("前置参考", result)
        finally:
            mod.search_original_text = orig_search


if __name__ == "__main__":
    unittest.main()
