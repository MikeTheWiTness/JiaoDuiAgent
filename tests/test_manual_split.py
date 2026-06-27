import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manual_split import split_by_manual_markers


class TestManualSplitNormal(unittest.TestCase):
    def test_single_problem_pair(self):
        md = (
            "###### 题目开始 ######\n"
            "这是第一题的内容\n"
            "第二行内容\n"
            "###### 题目结束 ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("这是第一题的内容", result[0]["content"])
        self.assertIn("第二行内容", result[0]["content"])

    def test_multiple_problems(self):
        md = (
            "###### 题目开始 ######\n"
            "第一题内容\n"
            "###### 题目结束 ######\n"
            "###### 题目开始 ######\n"
            "第二题内容\n"
            "###### 题目结束 ######\n"
            "###### 题目开始 ######\n"
            "第三题内容\n"
            "###### 题目结束 ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 3)
        self.assertIn("第一题", result[0]["content"])
        self.assertIn("第二题", result[1]["content"])
        self.assertIn("第三题", result[2]["content"])

    def test_outside_content_discarded(self):
        md = (
            "开头引言内容\n"
            "这里是说明文字\n"
            "###### 题目开始 ######\n"
            "题目正文\n"
            "###### 题目结束 ######\n"
            "中间过渡文字\n"
            "###### 题目开始 ######\n"
            "第二题正文\n"
            "###### 题目结束 ######\n"
            "结尾总结文字\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 2)
        self.assertNotIn("引言", result[0]["content"])
        self.assertNotIn("说明", result[0]["content"])
        self.assertNotIn("过渡", result[1]["content"])
        self.assertNotIn("总结", result[1]["content"])


class TestManualSplitErrors(unittest.TestCase):
    def test_no_markers_raises_error(self):
        md = "这是一段没有任何标记的文本\n只有普通内容\n"
        with self.assertRaises(ValueError) as ctx:
            split_by_manual_markers(md)
        self.assertIn("标记", str(ctx.exception))

    def test_missing_end_marker_raises_error(self):
        md = (
            "###### 题目开始 ######\n"
            "第一题内容\n"
            "###### 题目结束 ######\n"
            "###### 题目开始 ######\n"
            "第二题内容（没有结束标记）\n"
        )
        with self.assertRaises(ValueError) as ctx:
            split_by_manual_markers(md)
        self.assertIn("配对", str(ctx.exception))

    def test_end_without_start_raises_error(self):
        md = (
            "###### 题目结束 ######\n"
            "###### 题目开始 ######\n"
            "第一题内容\n"
            "###### 题目结束 ######\n"
        )
        with self.assertRaises(ValueError) as ctx:
            split_by_manual_markers(md)
        self.assertIn("配对", str(ctx.exception))

    def test_empty_content_raises_error(self):
        md = ""
        with self.assertRaises(ValueError) as ctx:
            split_by_manual_markers(md)
        self.assertIn("标记", str(ctx.exception))

    def test_only_start_marker_raises_error(self):
        md = "###### 题目开始 ######\n只有开始没有结束\n"
        with self.assertRaises(ValueError) as ctx:
            split_by_manual_markers(md)
        self.assertIn("配对", str(ctx.exception))


class TestManualSplitEdgeCases(unittest.TestCase):
    def test_extra_spaces_in_marker(self):
        md = (
            "######  题目开始  ######\n"
            "题目内容\n"
            "######  题目结束  ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("题目内容", result[0]["content"])

    def test_empty_problem_content(self):
        md = (
            "###### 题目开始 ######\n"
            "###### 题目结束 ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "")

    def test_marker_not_on_own_line(self):
        md = (
            "前面文字 ###### 题目开始 ###### 后面文字\n"
            "题目内容\n"
            "###### 题目结束 ######\n"
        )
        with self.assertRaises(ValueError):
            split_by_manual_markers(md)

    def test_preserves_whitespace_in_content(self):
        md = (
            "###### 题目开始 ######\n"
            "  缩进的内容\n"
            "\t制表符内容\n"
            "普通内容\n"
            "###### 题目结束 ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertIn("  缩进的内容", result[0]["content"])
        self.assertIn("\t制表符内容", result[0]["content"])

    def test_content_contains_marker_lookalike(self):
        md = (
            "###### 题目开始 ######\n"
            "正文里提到了###### 题目开始 ######但不是单独一行\n"
            "还有###### 题目结束 ######也在正文里\n"
            "###### 题目结束 ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("正文里提到了", result[0]["content"])


if __name__ == "__main__":
    unittest.main()
