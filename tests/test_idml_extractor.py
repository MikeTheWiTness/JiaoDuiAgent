"""测试 core/idml_extractor.py 的段落过滤判定（_is_useless）。

覆盖：
- 纯数字短行（题号 vs 页码）上下文判定
- 常规无用内容过滤
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.idml_extractor import _is_useless


class TestIsUseless(unittest.TestCase):
    """回归：≤3 位纯数字行不得无条件当页码丢弃（题号"12"被误删）。"""

    def test_short_number_between_sentences_kept(self):
        """前段以句末标点结尾 → 数字是下一句的题号/分值，保留"""
        self.assertFalse(_is_useless("12", "NormalParagraphStyle",
                                     prev_text="阅读下面的文字，完成下面小题。",
                                     next_text="下列对文中画波浪线部分的断句"))

    def test_short_number_before_numbered_item_kept(self):
        """后段以编号开头 → 当前数字是编号列表项，保留"""
        self.assertFalse(_is_useless("12", "NormalParagraphStyle",
                                     prev_text="非题干续行",
                                     next_text="12．下列对文中加点词"))

    def test_short_number_isolated_is_page_number(self):
        """前后均非句末/编号上下文 → 独立页码，过滤"""
        self.assertTrue(_is_useless("12", "NormalParagraphStyle",
                                    prev_text="正文结束没有句末标点",
                                    next_text="下一段开始"))

    def test_short_number_no_context_filtered(self):
        """无上下文信息时保持原行为（当页码过滤）"""
        self.assertTrue(_is_useless("12", "NormalParagraphStyle"))

    def test_four_digit_year_kept(self):
        """4 位数字（年份）不受影响"""
        self.assertFalse(_is_useless("2026", "NormalParagraphStyle"))

    def test_empty_text(self):
        self.assertTrue(_is_useless("  ", "NormalParagraphStyle"))
        self.assertTrue(_is_useless("", "NormalParagraphStyle"))

    def test_word_count_rules(self):
        """字数要求行（600字等）过滤"""
        self.assertTrue(_is_useless("600字", "NormalParagraphStyle"))
        self.assertTrue(_is_useless("800字", "NormalParagraphStyle"))

    def test_circle_number_rules(self):
        """圆圈序号短行过滤"""
        self.assertTrue(_is_useless("①", "NormalParagraphStyle"))
        self.assertTrue(_is_useless("①②", "NormalParagraphStyle"))

    def test_normal_text_kept(self):
        self.assertFalse(_is_useless("这是一段正常的正文内容。", "NormalParagraphStyle"))


if __name__ == "__main__":
    unittest.main()
