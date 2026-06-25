import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.smart_split import parse_problem_tags, smart_split_with_callable, smart_split, SMART_SPLIT_PROMPT


class TestParseProblemTags(unittest.TestCase):
    def test_single_problem(self):
        text = "<problem>第一题内容</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "第一题内容")

    def test_multiple_problems(self):
        text = "<problem>第一题</problem>中间文字<problem>第二题</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"], "第一题")
        self.assertEqual(result[1]["content"], "第二题")

    def test_outside_content_discarded(self):
        text = "开头引言<problem>题目内容</problem>结尾总结"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertNotIn("引言", result[0]["content"])
        self.assertNotIn("总结", result[0]["content"])

    def test_no_tags_returns_empty(self):
        text = "没有任何标记的纯文本"
        result = parse_problem_tags(text)
        self.assertEqual(result, [])

    def test_multiline_problem(self):
        text = "<problem>第一行\n第二行\n第三行</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertIn("第一行", result[0]["content"])
        self.assertIn("第二行", result[0]["content"])
        self.assertIn("第三行", result[0]["content"])


class TestSmartSplitMain(unittest.TestCase):
    def test_successful_first_call(self):
        original = "引言\n第一题内容\n过渡\n第二题内容\n结尾"
        mock_result = (
            "引言\n<problem>第一题内容</problem>\n过渡\n<problem>第二题内容</problem>\n结尾"
        )
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            return mock_result

        result = smart_split_with_callable(original, mock_llm_call)
        self.assertEqual(len(result), 2)
        self.assertIn("第一题", result[0]["content"])
        self.assertIn("第二题", result[1]["content"])
        self.assertEqual(call_count[0], 1)

    def test_first_call_fails_second_succeeds(self):
        original = "题目内容"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                return "没有任何标记的错误返回"
            return "<problem>题目内容</problem>"

        result = smart_split_with_callable(original, mock_llm_call)
        self.assertEqual(len(result), 1)
        self.assertEqual(call_count[0], 2)

    def test_both_calls_fail_fallback_to_single(self):
        original = "全文内容作为一个单元"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            return "完全没有标记的垃圾输出"

        result = smart_split_with_callable(original, mock_llm_call)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], original)
        self.assertEqual(call_count[0], 2)

    def test_empty_tags_result_fallback(self):
        original = "全文内容"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            return "<problem></problem>"

        result = smart_split_with_callable(original, mock_llm_call)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], original)
        self.assertEqual(call_count[0], 2)


class TestSmartSplitEdgeCases(unittest.TestCase):
    def test_tags_with_newlines(self):
        text = "<problem>\n题目内容\n</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "题目内容")

    def test_nested_like_pattern_not_confused(self):
        text = "<problem>正文里有 <problem> 这个词</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertIn("正文里有", result[0]["content"])

    def test_prompt_exists(self):
        self.assertIsInstance(SMART_SPLIT_PROMPT, str)
        self.assertIn("<problem>", SMART_SPLIT_PROMPT)
        self.assertIn("不修改原文", SMART_SPLIT_PROMPT)

    def test_smart_split_function_exists(self):
        self.assertTrue(callable(smart_split))

    def test_llm_exception_triggers_retry(self):
        original = "题目内容"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("API 超时")
            return "<problem>题目内容</problem>"

        result = smart_split_with_callable(original, mock_llm_call)
        self.assertEqual(len(result), 1)
        self.assertEqual(call_count[0], 2)

    def test_both_llm_exceptions_fallback(self):
        original = "全文"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            raise RuntimeError("API 挂了")

        result = smart_split_with_callable(original, mock_llm_call)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], original)
        self.assertEqual(call_count[0], 2)

    def test_output_format_compatible_with_manual_split(self):
        text = "<problem>题目一</problem><problem>题目二</problem>"
        result = parse_problem_tags(text)
        for item in result:
            self.assertIn("content", item)
            self.assertIsInstance(item["content"], str)


if __name__ == "__main__":
    unittest.main()
