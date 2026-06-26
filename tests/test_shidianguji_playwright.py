"""测试 Playwright 识典古籍提取模块（ADR 0004 决策 1 + Issue #3）

验证：软依赖设计——Playwright 可用时提取正文，不可用时静默不可用。
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestShidiangujiPlaywright(unittest.TestCase):
    """验证 Playwright 模块的公共接口和行为契约"""

    def test_is_playwright_available_returns_bool(self):
        from shared.shidianguji_playwright import is_playwright_available
        result = is_playwright_available()
        self.assertIsInstance(result, bool,
                              "必须返回布尔值，不能抛异常")

    def test_module_imports_without_playwright_installed(self):
        from shared import shidianguji_playwright
        self.assertTrue(True)

    def test_search_and_extract_returns_none_for_empty_key(self):
        """空关键词应返回 None"""
        from shared.shidianguji_playwright import is_playwright_available, search_and_extract
        if not is_playwright_available():
            self.skipTest("Playwright 不可用")
        result = search_and_extract("")
        self.assertIsNone(result)

    def test_extract_chapter_returns_dict_or_none(self):
        from shared.shidianguji_playwright import is_playwright_available, extract_chapter
        if not is_playwright_available():
            self.skipTest("Playwright 不可用")
        result = extract_chapter("SK0724", "1l9yzpxkqkr3b")
        if result is None:
            self.skipTest("识典古籍暂时不可用")
        self.assertIsInstance(result, dict)
        self.assertIn("title", result)
        self.assertIn("text", result)
        self.assertGreater(len(result["text"]), 100)

    def test_search_and_extract_known_passage(self):
        from shared.shidianguji_playwright import is_playwright_available, search_and_extract
        if not is_playwright_available():
            self.skipTest("Playwright 不可用")
        result = search_and_extract("学而时习之")
        if result is None:
            self.skipTest("识典古籍搜索暂时不可用")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 20,
                           "应该返回至少 20 字正文")
        # 返回的正文应包含搜索关键词的子串（无标点版）
        import re
        clean = re.sub(r'[^一-鿿]', '', "学而时习之")
        self.assertIn(clean, re.sub(r'[^一-鿿]', '', result),
                      "搜索结果应包含搜索关键词")

    def test_keyword_verification_in_result(self):
        """如果返回正文，其中必含搜索关键词的子串（去标点）"""
        from shared.shidianguji_playwright import is_playwright_available, search_and_extract
        if not is_playwright_available():
            self.skipTest("Playwright 不可用")
        result = search_and_extract("韦凑字彦宗京兆万年人")
        if result is None:
            self.skipTest("识典古籍搜索暂时不可用")
        import re
        key_clean = re.sub(r'[^一-鿿]', '', "韦凑字彦宗京兆万年人")[:5]
        text_clean = re.sub(r'[^一-鿿]', '', result)
        self.assertIn(key_clean, text_clean,
                      f"正文应包含搜索关键词的前5字 '{key_clean}'")

    def test_module_exports_correct_functions(self):
        from shared import shidianguji_playwright as sp
        for name in ["is_playwright_available", "extract_chapter", "search_and_extract"]:
            self.assertTrue(hasattr(sp, name), f"模块应导出 {name}()")
            self.assertTrue(callable(getattr(sp, name)),
                            f"{name} 必须是可调用的")


if __name__ == "__main__":
    unittest.main()
