import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.manual_split import split_by_manual_markers, split_by_unit_markers, parse_unit_markers


# ─── 已有的 manual split 测试（保持不变） ──────────────────────

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


class TestManualSplitPandocEscaped(unittest.TestCase):
    """pandoc 转换会把行首 # 转义成 \\#，标记变成 \\###### 题目开始 \\######。

    正则需容忍转义，否则匹配不到 → 抛 ManualMarkerError → 调用方未捕获
    → 转换线程静默死亡、UI 卡住。回归 bug：试卷模式 post_process_md_zw
    不还原 \\#（讲义模式 fix_latex_escapes 会还原，故讲义不触发）。
    """

    def test_pandoc_escaped_first_hash(self):
        # pandoc 实际行为：每组首个 # 前加反斜杠
        md = (
            r"\###### 题目开始 \######" "\n"
            "第一题内容\n"
            r"\###### 题目结束 \######" "\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("第一题内容", result[0]["content"])

    def test_unescaped_markers_still_work(self):
        # 回归保护：未转义标记仍正常切
        md = (
            "###### 题目开始 ######\n"
            "第一题内容\n"
            "###### 题目结束 ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("第一题内容", result[0]["content"])

    def test_per_hash_escaped(self):
        # 防御：每个 # 都被转义的形态（\\#\\#\\#\\#\\#\\#）
        md = (
            r"\#\#\#\#\#\# 题目开始 \#\#\#\#\#\#" "\n"
            "第一题内容\n"
            r"\#\#\#\#\#\# 题目结束 \#\#\#\#\#\#" "\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("第一题内容", result[0]["content"])

    def test_mixed_escaped_and_unescaped_problems(self):
        # 一题转义、一题未转义，都应切出
        md = (
            r"\###### 题目开始 \######" "\n"
            "第一题\n"
            r"\###### 题目结束 \######" "\n"
            "###### 题目开始 ######\n"
            "第二题\n"
            "###### 题目结束 ######\n"
        )
        result = split_by_manual_markers(md)
        self.assertEqual(len(result), 2)
        self.assertIn("第一题", result[0]["content"])
        self.assertIn("第二题", result[1]["content"])


if __name__ == "__main__":
    unittest.main()


# ─── 统一的单元标记测试（ADR-0017 决策5） ──────────────────────

class TestSplitByUnitMarkers(unittest.TestCase):
    """测试统一的 split_by_unit_markers（替代 split_by_manual_markers + split_by_knowledge_markers）。"""

    def test_single_unit(self):
        md = (
            "###### 单元开始 ######\n"
            "这是第一单元的内容\n"
            "第二行\n"
            "###### 单元结束 ######\n"
        )
        result = split_by_unit_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("第一单元的内容", result[0]["content"])

    def test_multiple_units(self):
        md = (
            "###### 单元开始 ######\n"
            "单元1内容\n"
            "###### 单元结束 ######\n"
            "###### 单元开始 ######\n"
            "单元2内容\n"
            "###### 单元结束 ######\n"
            "###### 单元开始 ######\n"
            "单元3内容\n"
            "###### 单元结束 ######\n"
        )
        result = split_by_unit_markers(md)
        self.assertEqual(len(result), 3)

    def test_outside_content_discarded(self):
        md = (
            "开头引言\n"
            "###### 单元开始 ######\n"
            "单元正文\n"
            "###### 单元结束 ######\n"
            "中间过渡\n"
            "###### 单元开始 ######\n"
            "第二单元\n"
            "###### 单元结束 ######\n"
            "结尾总结\n"
        )
        result = split_by_unit_markers(md)
        self.assertEqual(len(result), 2)
        self.assertNotIn("引言", result[0]["content"])
        self.assertNotIn("过渡", result[1]["content"])

    def test_no_markers_raises_error(self):
        md = "没有标记的文本"
        with self.assertRaises(ValueError) as ctx:
            split_by_unit_markers(md)
        self.assertIn("标记", str(ctx.exception))

    def test_unpaired_marker_raises_error(self):
        md = (
            "###### 单元开始 ######\n"
            "内容没有结束标记\n"
        )
        with self.assertRaises(ValueError):
            split_by_unit_markers(md)

    def test_pandoc_escaped_markers(self):
        md = (
            r"\###### 单元开始 \######" "\n"
            "单元内容\n"
            r"\###### 单元结束 \######" "\n"
        )
        result = split_by_unit_markers(md)
        self.assertEqual(len(result), 1)
        self.assertIn("单元内容", result[0]["content"])


class TestParseUnitMarkers(unittest.TestCase):
    """测试共用的 parse_unit_markers() 解析器。"""

    def test_parse_single_unit(self):
        text = (
            "###### 单元开始 ######\n"
            "内容A\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"].strip(), "内容A")

    def test_parse_multiple_units(self):
        text = (
            "###### 单元开始 ######\n"
            "单元1\n"
            "###### 单元结束 ######\n"
            "###### 单元开始 ######\n"
            "单元2\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 2)

    def test_parse_empty_text(self):
        with self.assertRaises(ValueError):
            parse_unit_markers("")

    def test_parse_no_markers(self):
        with self.assertRaises(ValueError):
            parse_unit_markers("没有标记的普通文本")

    def test_parse_content_contains_marker_lookalike(self):
        """正文中包含类似标记的文字但不在一行时不应干扰。"""
        text = (
            "###### 单元开始 ######\n"
            "正文里提到了###### 单元开始 ######但不是单独一行\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertIn("提到了", result[0]["content"])

    def test_parse_extra_spaces_in_marker(self):
        text = (
            "######  单元开始  ######\n"
            "内容\n"
            "######  单元结束  ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)

    def test_parse_empty_unit(self):
        text = (
            "###### 单元开始 ######\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "")

    def test_parse_pandoc_escaped(self):
        text = (
            r"\###### 单元开始 \######" "\n"
            "内容\n"
            r"\###### 单元结束 \######" "\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertIn("内容", result[0]["content"])


if __name__ == "__main__":
    unittest.main()
