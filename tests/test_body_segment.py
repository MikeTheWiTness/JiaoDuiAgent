# -*- coding: utf-8 -*-
"""extract_body_segment 与前置 diff 噪音修复的回归测试。

用 output/拆题结果/高中语文教研实习生笔试试卷 下的真实题目做 fixture：
- 第1题（韦凑传，含批注）、第4题（戴胄传，含下划线/波浪线）→ 文言文，应切出正文段
- 第3题（拉奥孔，现代文）→ 不应切出（返回 None）

并验证 preprocess_for_proofread 注入的「前置参考」差异条数从修复前的 111/51
降到个位数～十几条（回归护栏），且韦凑题的真错误（雇→顾 等）确实出现在差异列表里。
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.chinese_classics_tools import (
    extract_body_segment,
    preprocess_for_proofread,
    _clean_for_matching,
)
import shared.chinese_classics_tools as cc

PAPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "拆题结果", "高中语文教研实习生笔试试卷",
)
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_search_results")


def _read(q_num):
    with open(os.path.join(PAPER, f"第{q_num}题", f"第{q_num}题.md"), encoding="utf-8") as f:
        return f.read()


class TestExtractBodySegment(unittest.TestCase):
    def test_weicou_body_segment(self):
        body = extract_body_segment(_read(1))
        self.assertIsNotNone(body, "韦凑题应能切出正文段")
        clean = _clean_for_matching(body)
        self.assertTrue(clean.startswith("韦凑字彦宗"), f"正文应以「韦凑字彦宗」开头，实际: {clean[:20]}")
        # 不应混入题干 / 出处
        self.assertNotIn("对下列", body)
        self.assertNotIn("节选自", body)
        # 不应混入断句选项的斜线（题干特有）
        self.assertNotIn("下列对文中", body)

    def test_daizhou_body_segment(self):
        body = extract_body_segment(_read(4))
        self.assertIsNotNone(body, "戴胄题应能切出正文段")
        clean = _clean_for_matching(body)
        # 第4题正文以 <波浪线>戴胄忠清公直 起头，清洗后应为「戴胄忠清公直」
        self.assertTrue(clean.startswith("戴胄忠清公直"), f"正文应以「戴胄忠清公直」开头，实际: {clean[:20]}")
        self.assertNotIn("下列对文中", body)
        self.assertNotIn("节选自", body)

    def test_modern_returns_none(self):
        # 第3题是现代文（阅读下面的文字），引导语不含「文言文/古诗/…」→ 返回 None
        body = extract_body_segment(_read(3))
        self.assertIsNone(body, "现代文题不应切出正文段")

    def test_empty_input(self):
        self.assertIsNone(extract_body_segment(""))
        self.assertIsNone(extract_body_segment(None))
        self.assertIsNone(extract_body_segment("   \n  "))

    def test_no_leadin_returns_none(self):
        self.assertIsNone(extract_body_segment("韦凑字彦宗，京兆万年人。"))


class TestPreprocessDiffNoise(unittest.TestCase):
    """端到端：monkeypatch 联网搜索为本地全文，验证 diff 噪音已消除。"""

    @staticmethod
    def _run(q_num, name):
        with open(os.path.join(DATA, f"{name}_full.txt"), encoding="utf-8") as f:
            saved = f.read()
        real = cc.search_original_text
        cc.search_original_text = lambda tt, sk: saved
        try:
            md = _read(q_num)
            q_dir = os.path.join(PAPER, f"第{q_num}题")
            return preprocess_for_proofread(md, q_dir=q_dir)
        finally:
            cc.search_original_text = real

    @staticmethod
    def _count_diffs(reference_md):
        import re
        return len(re.findall(r'^\d+\. 第\d+位', reference_md, flags=re.MULTILINE))

    def test_weicou_diff_noise_eliminated(self):
        md = self._run(1, "weicou")
        self.assertIn("## 前置参考", md, "韦凑题应注入前置参考")
        n = self._count_diffs(md)
        # 修复前 111 条；修复后应远低于 20（6 条真错误 + 少量节选边界 delete_from_original）
        self.assertLess(n, 20, f"韦凑题差异条数 {n} 过高，疑似整道题又进了 diff")
        # 真错误应出现在差异列表里
        self.assertIn("雇", md)  # 原文「雇」 vs 题目「顾」
        self.assertIn("陜", md)  # 原文「陜」 vs 题目「陕」（异体字）

    def test_daizhou_diff_noise_eliminated(self):
        md = self._run(4, "daizhou")
        self.assertIn("## 前置参考", md, "戴胄题应注入前置参考")
        n = self._count_diffs(md)
        # 修复前 51 条；修复后应远低于 20
        self.assertLess(n, 20, f"戴胄题差异条数 {n} 过高，疑似整道题又进了 diff")


if __name__ == "__main__":
    unittest.main(verbosity=2)
