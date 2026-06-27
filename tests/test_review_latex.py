import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.review_latex import (
    generate_review_latex,
    _escape_text,
    _replace_markers_with_circled_numbers,
)


class TestEscapeText(unittest.TestCase):
    def test_escape_special_chars(self):
        text = "测试&%$_{}"
        escaped = _escape_text(text)
        self.assertNotIn("&", escaped.replace("\\&", ""))
        self.assertIn("\\&", escaped)
        self.assertIn("\\%", escaped)

    def test_normal_text_unchanged(self):
        text = "普通中文文本"
        self.assertEqual(_escape_text(text), text)

    def test_empty_text(self):
        self.assertEqual(_escape_text(""), "")


class TestMarkerReplacement(unittest.TestCase):
    def test_single_marker(self):
        md = '原文<批注 id=1><原>此处</原><改>批注内容</改></批注>继续'
        result = _replace_markers_with_circled_numbers(md)
        self.assertIn("①", result)
        self.assertNotIn('批注', result)

    def test_multiple_markers(self):
        md = '开头<批注 id=1><原>此处</原><改>内容1</改></批注>中间<批注 id=2><原>此处</原><改>内容2</改></批注>结尾'
        result = _replace_markers_with_circled_numbers(md)
        self.assertIn("①", result)
        self.assertIn("②", result)

    def test_no_markers(self):
        md = "普通文本，没有批注"
        result = _replace_markers_with_circled_numbers(md)
        self.assertEqual(result, md)


class TestGenerateReviewLatex(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_files(self, md_content, review_data):
        md_path = os.path.join(self.tmpdir, "test.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        import json
        json_path = os.path.join(self.tmpdir, "proofread_result.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(review_data, f, ensure_ascii=False)

        return md_path, json_path

    def test_generate_returns_tex_path(self):
        md = '原文<批注 id=1><原>此处</原><改>批注内容</改></批注>结尾'
        review_data = {
            "judgments": [
                {"id": 1, "verdict": "正确", "reason": "确实是错字"}
            ],
            "supplements": ["遗漏的错误"]
        }
        md_path, json_path = self._write_files(md, review_data)
        out_path = os.path.join(self.tmpdir, "output.tex")

        result = generate_review_latex(md_path, json_path, out_path, title="测试")
        self.assertTrue(os.path.exists(result))
        self.assertTrue(result.endswith(".tex"))

    def test_tex_contains_title(self):
        md = "内容"
        review_data = {"judgments": [], "supplements": []}
        md_path, json_path = self._write_files(md, review_data)
        out_path = os.path.join(self.tmpdir, "output.tex")

        generate_review_latex(md_path, json_path, out_path, title="测试标题")

        with open(out_path, 'r', encoding='utf-8') as f:
            tex = f.read()
        self.assertIn("测试标题", tex)

    def test_tex_contains_original_text(self):
        md = "这是原文内容"
        review_data = {"judgments": [], "supplements": []}
        md_path, json_path = self._write_files(md, review_data)
        out_path = os.path.join(self.tmpdir, "output.tex")

        generate_review_latex(md_path, json_path, out_path, title="测试")

        with open(out_path, 'r', encoding='utf-8') as f:
            tex = f.read()
        self.assertIn("这是原文内容", tex)

    def test_tex_contains_judgments(self):
        md = '内容<批注 id=1><原>此处</原><改>批注内容</改></批注>'
        review_data = {
            "judgments": [
                {"id": 1, "verdict": "正确", "reason": "说明文字"}
            ],
            "supplements": []
        }
        md_path, json_path = self._write_files(md, review_data)
        out_path = os.path.join(self.tmpdir, "output.tex")

        generate_review_latex(md_path, json_path, out_path, title="测试")

        with open(out_path, 'r', encoding='utf-8') as f:
            tex = f.read()
        self.assertIn("批注1", tex)
        self.assertIn("正确", tex)
        self.assertIn("说明文字", tex)

    def test_tex_contains_supplements(self):
        md = "内容"
        review_data = {
            "judgments": [],
            "supplements": ["第一处补充", "第二处补充"]
        }
        md_path, json_path = self._write_files(md, review_data)
        out_path = os.path.join(self.tmpdir, "output.tex")

        generate_review_latex(md_path, json_path, out_path, title="测试")

        with open(out_path, 'r', encoding='utf-8') as f:
            tex = f.read()
        self.assertIn("补充发现", tex)
        self.assertIn("第一处补充", tex)
        self.assertIn("第二处补充", tex)

    def test_three_verdicts_display(self):
        md = 'a<批注 id=1><原>此处</原><改>1</改></批注>b<批注 id=2><原>此处</原><改>2</改></批注>c<批注 id=3><原>此处</原><改>3</改></批注>d'
        review_data = {
            "judgments": [
                {"id": 1, "verdict": "正确", "reason": "对"},
                {"id": 2, "verdict": "有误", "reason": "错"},
                {"id": 3, "verdict": "部分正确", "reason": "部分"},
            ],
            "supplements": []
        }
        md_path, json_path = self._write_files(md, review_data)
        out_path = os.path.join(self.tmpdir, "output.tex")

        generate_review_latex(md_path, json_path, out_path, title="测试")

        with open(out_path, 'r', encoding='utf-8') as f:
            tex = f.read()
        self.assertIn("正确", tex)
        self.assertIn("有误", tex)
        self.assertIn("部分正确", tex)

    def test_circled_numbers_in_text(self):
        md = '原文<批注 id=1><原>此处</原><改>内容</改></批注>继续'
        review_data = {
            "judgments": [
                {"id": 1, "verdict": "正确", "reason": ""}
            ],
            "supplements": []
        }
        md_path, json_path = self._write_files(md, review_data)
        out_path = os.path.join(self.tmpdir, "output.tex")

        generate_review_latex(md_path, json_path, out_path, title="测试")

        with open(out_path, 'r', encoding='utf-8') as f:
            tex = f.read()
        self.assertIn("①", tex)


if __name__ == "__main__":
    unittest.main()
