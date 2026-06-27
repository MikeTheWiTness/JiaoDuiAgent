import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.review_mode import (
    is_review_mode,
    build_review_prompt,
    parse_review_result,
    extract_comments_from_md,
)


class TestIsReviewMode(unittest.TestCase):
    def test_review_mode_recognized(self):
        self.assertTrue(is_review_mode("批注评审"))

    def test_other_modes_not_recognized(self):
        self.assertFalse(is_review_mode("讲义"))
        self.assertFalse(is_review_mode("试卷"))
        self.assertFalse(is_review_mode("自由校对"))


class TestExtractCommentsFromMd(unittest.TestCase):
    def test_extract_single_comment(self):
        md = '这是原文<批注 id=1><原>此处</原><改>这里有错字</改></批注>继续原文'
        comments = extract_comments_from_md(md)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["id"], 1)
        self.assertIn("有错字", comments[0]["text"])

    def test_extract_multiple_comments(self):
        md = '第一段<批注 id=1><原>此处</原><改>错误1</改></批注>中间<批注 id=2><原>此处</原><改>错误2</改></批注>结尾'
        comments = extract_comments_from_md(md)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["id"], 1)
        self.assertEqual(comments[1]["id"], 2)

    def test_no_comments(self):
        md = "普通文本，没有批注"
        comments = extract_comments_from_md(md)
        self.assertEqual(comments, [])

    def test_extract_context(self):
        md = '上下文开头被批注文字<批注 id=1><原>此处</原><改>批注内容</改></批注>上下文结尾'
        comments = extract_comments_from_md(md)
        self.assertEqual(len(comments), 1)
        self.assertIn("context_before", comments[0])
        self.assertIn("context_after", comments[0])


class TestBuildReviewPrompt(unittest.TestCase):
    def test_prompt_contains_instructions_with_comments(self):
        md = '原文<批注 id=1><原>此处</原><改>有错字</改></批注>'
        prompt = build_review_prompt(md)
        self.assertIn("批注评审", prompt)

    def test_prompt_mentions_judgment(self):
        md = '原文<批注 id=1><原>此处</原><改>有错字</改></批注>'
        prompt = build_review_prompt(md)
        self.assertIn("正确", prompt)
        self.assertIn("错误", prompt)

    def test_prompt_mentions_supplement(self):
        md = '原文<批注 id=1><原>此处</原><改>有错字</改></批注>'
        prompt = build_review_prompt(md)
        self.assertIn("补充", prompt)

    def test_prompt_without_comments_uses_proofread(self):
        md = "纯文本无批注"
        prompt = build_review_prompt(md)
        self.assertIn("全文校对", prompt)
        self.assertNotIn('批注评审', prompt)

    def test_empty_md_uses_proofread(self):
        prompt = build_review_prompt("")
        self.assertIn("全文校对", prompt)
        self.assertTrue(len(prompt) > 0)


class TestParseReviewResult(unittest.TestCase):
    def test_parse_correct_judgment(self):
        result = """
## 批注评审结果

### 批注1
- 评判：正确
- 说明：确实是错字

### 补充发现
- 还有一处遗漏
"""
        parsed = parse_review_result(result)
        self.assertIn("judgments", parsed)
        self.assertGreaterEqual(len(parsed["judgments"]), 1)
        self.assertEqual(parsed["judgments"][0]["id"], 1)
        self.assertEqual(parsed["judgments"][0]["verdict"], "正确")

    def test_parse_multiple_judgments(self):
        result = """
### 批注1
- 评判：正确

### 批注2
- 评判：有误
- 说明：不是错字
"""
        parsed = parse_review_result(result)
        self.assertEqual(len(parsed["judgments"]), 2)
        self.assertEqual(parsed["judgments"][1]["verdict"], "有误")

    def test_parse_supplement(self):
        result = """
### 批注1
- 评判：正确

### 补充发现
- 第一处遗漏错误
- 第二处遗漏错误
"""
        parsed = parse_review_result(result)
        self.assertIn("supplements", parsed)
        self.assertGreaterEqual(len(parsed["supplements"]), 2)

    def test_empty_result(self):
        parsed = parse_review_result("")
        self.assertEqual(parsed["judgments"], [])
        self.assertEqual(parsed["supplements"], [])

    def test_partial_correct_verdict(self):
        result = """
### 批注1
- 评判：部分正确
- 说明：部分对部分错
"""
        parsed = parse_review_result(result)
        self.assertEqual(parsed["judgments"][0]["verdict"], "部分正确")


class TestSubjectReviewMode(unittest.TestCase):
    def setUp(self):
        import importlib.util
        subject_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "subjects", "高中语文v1.1"
        )
        spec = importlib.util.spec_from_file_location(
            "yuwen_subject",
            os.path.join(subject_dir, "subject.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.app = mod.SubjectApp(subject_dir)

    def test_ui_features_has_review_mode(self):
        features = self.app.get_ui_features()
        self.assertIn("批注评审", features["show_source_modes"])

    def test_four_source_modes_total(self):
        features = self.app.get_ui_features()
        self.assertGreaterEqual(len(features["show_source_modes"]), 4)


if __name__ == "__main__":
    unittest.main()
