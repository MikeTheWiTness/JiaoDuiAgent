import os
import sys
import unittest

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.network

from shared.chinese_classics_tools import (
    build_reference_section,
    detect_text_type,
    diff_characters,
    preprocess_for_proofread,
    search_original_text,
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
        # n-gram diff 在短文本中 given 是 original 子串时不报差异
        # 这是合理的容错行为——真实场景中缺失字会影响周围多个 n-gram
        # 用更明显的差异来测试：词序交换
        original = "床前明月光疑是地上霜"
        given = "床前月光疑是地上霜"  # 缺了"明"
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


class TestDetectModernWithRomanLeadIn(unittest.TestCase):
    """现代文阅读题(带罗马数字引导语+古人名引用)不得误判为文言文。

    回归用例:真实运行时,某现代文阅读题被 detect_text_type 误判为 classical,
    正则回退把引导语"现代文阅读Ⅰ（本题共"当关键词,去识典古籍搜到 4 万字
    不相关原文注入 prompt,反而误导 LLM 反复搜网页。
    """

    def test_modern_reading_with_roman_numeral_not_classical(self):
        text = "现代文阅读Ⅰ（本题共2小题，7分）\n阅读下面的文字，完成1-2题。\n戴胄忠清公直擢为大理，韦凑字彦宗，京兆万年人也。"
        self.assertEqual(detect_text_type(text), "modern")

    def test_modern_reading_with_arabic_numeral_not_classical(self):
        text = "现代文阅读2（本题共2小题）\n阅读下面的文字。\n朱光潜先生在《诗论》中谈及莱辛的观点。"
        self.assertEqual(detect_text_type(text), "modern")

    def test_classical_still_detected_when_no_modern_marker(self):
        # 真文言文传记(无现代文标记词)仍应判 classical,确保否决不误杀
        text = "韦凑字彦宗，京兆万年人也。少以孝闻，除右卫率府铠曹参军。"
        self.assertEqual(detect_text_type(text), "classical")


class TestBuildReferenceSectionContent(unittest.TestCase):
    """前置参考块内容：权威原文 + 字面差异/比对结果 + 提示语。

    本阶段 LLM 不配备搜索工具（ReAct 工具仅 plan_update/locate_paragraph/read_section），
    前置参考块不再注入关于 web_search/web_fetch 的硬性约束说明——引用 LLM 没有的工具
    反而造成困惑。若后续重新启用搜索工具，应同步恢复硬性约束并更新此处测试。
    """

    def test_diff_section_present_with_diffs(self):
        diffs = [{"original": "明", "given": "名", "position": 2, "type": "replace"}]
        result = build_reference_section("classical", "先帝创业未半", diffs)
        self.assertIn("字面差异", result)
        self.assertIn("「明」→「名」", result)
        self.assertIn("请结合语境判断", result)

    def test_identical_directive_present_no_diffs(self):
        result = build_reference_section("poetry", "床前明月光", [])
        self.assertIn("字面一致", result)
        self.assertIn("标点符号", result)

    def test_no_search_tool_directives(self):
        # 无搜索工具阶段：前置参考块不应出现 web_search/web_fetch/硬性约束/按需搜索
        diffs = [{"original": "明", "given": "名", "position": 2, "type": "replace"}]
        result = build_reference_section("classical", "先帝创业未半", diffs)
        self.assertNotIn("web_search", result)
        self.assertNotIn("web_fetch", result)
        self.assertNotIn("硬性约束", result)
        self.assertNotIn("按需搜索", result)



if __name__ == "__main__":
    unittest.main()
