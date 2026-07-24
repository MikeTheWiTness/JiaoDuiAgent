import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.web_tools import WebFetchTool


class TestShidiangujiSupport(unittest.TestCase):
    def test_web_fetch_has_shidianguji_method(self):
        tool = WebFetchTool()
        self.assertTrue(hasattr(tool, '_fetch_shidianguji'))

    def test_recognizes_shidianguji_url(self):
        tool = WebFetchTool()
        url = "https://www.shidianguji.com/search?q=韦凑"
        self.assertIn("shidianguji", tool.description)


class TestShidiangujiParser(unittest.TestCase):
    def test_parse_search_results(self):
        from shared.web_tools import _parse_shidianguji_search
        html = '''
        <html><body>
        <div class="search-result">
            <div class="result-item">
                <a href="/book/123/chapter/456">旧唐书·韦凑传</a>
                <p class="snippet">韦凑字彦宗，京兆万年人...</p>
            </div>
            <div class="result-item">
                <a href="/book/789/chapter/012">新唐书·韦凑传</a>
                <p class="snippet">韦凑，字彦宗...</p>
            </div>
        </div>
        </body></html>
        '''
        results = _parse_shidianguji_search(html)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("title", results[0])
        self.assertIn("url", results[0])
        self.assertIn("韦凑", results[0]["title"])

    def test_parse_detail_page(self):
        from shared.web_tools import _parse_shidianguji_detail
        html = '''
        <html><body>
        <h1>旧唐书·韦凑传</h1>
        <div class="content">
            <p>韦凑字彦宗，京兆万年人。</p>
            <p>永淳初，解褐婺州参军事。</p>
        </div>
        </body></html>
        '''
        text = _parse_shidianguji_detail(html)
        self.assertIn("韦凑字彦宗", text)
        self.assertIn("京兆万年人", text)

    def test_search_empty_result(self):
        from shared.web_tools import _parse_shidianguji_search
        html = '<html><body><div class="no-result">未找到相关结果</div></body></html>'
        results = _parse_shidianguji_search(html)
        self.assertEqual(results, [])


class TestChineseSubjectHasFetchTool(unittest.TestCase):
    def test_subject_has_web_fetch_tool(self):
        import importlib.util
        subject_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "subjects", "高中语文v3.0"
        )
        spec = importlib.util.spec_from_file_location(
            "yuwen_subject",
            os.path.join(subject_dir, "subject.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        app = mod.SubjectApp(subject_dir)
        tool_names = [t.name for t in app.tools]
        self.assertIn("web_fetch", tool_names)

    def test_tool_instructions_mentions_shidianguji(self):
        import importlib.util
        subject_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "subjects", "高中语文v3.0"
        )
        spec = importlib.util.spec_from_file_location(
            "yuwen_subject",
            os.path.join(subject_dir, "subject.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        app = mod.SubjectApp(subject_dir)
        instructions = app.get_tool_instructions()
        self.assertIn("识典古籍", instructions)


if __name__ == "__main__":
    unittest.main()
