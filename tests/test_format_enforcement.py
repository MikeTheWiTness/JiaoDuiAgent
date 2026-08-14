"""测试格式审查二级制：_enforce_format 程序初筛全部检查项 + enforce_and_fix 成败分支。

覆盖：
- 无问题报告直接通过
- 缺 ### 标记原文 / 无内联标记
- 缺 ### 修改原因
- 标记编号与修改原因编号缺失/多余
- 畸形标记（编号后缺 |）
- 标记原文含内部 ### 标题（前置参考）时边界正确
- enforce_and_fix 修正成功 / 修正失败回退原始
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.format_enforcement import _enforce_format, enforce_and_fix

OK_REPORT = """轻微问题

### 标记原文
编号：第1题
内容：
1．题目【1|错误|正确】

### 修改原因
1. 修正错误。
"""


class TestEnforceFormat(unittest.TestCase):
    def test_no_issue_passes(self):
        ok, issues = _enforce_format("无问题")
        self.assertTrue(ok)
        self.assertEqual(issues, "")

    def test_no_issue_with_punctuation_passes(self):
        ok, _ = _enforce_format("无问题。")
        self.assertTrue(ok)

    def test_no_issue_with_long_text_is_not_no_issue(self):
        """超过 10 字符的「无问题」开头文本不算无问题（需走结构检查）"""
        ok, issues = _enforce_format("无问题。整体质量良好。")
        self.assertFalse(ok)
        self.assertTrue(issues)

    def test_valid_report_passes(self):
        ok, issues = _enforce_format(OK_REPORT)
        self.assertTrue(ok, f"合格报告不应报问题: {issues}")

    def test_missing_marker_section(self):
        """缺 ### 标记原文 且无内联标记 → 报缺失"""
        report = "只有修改原因\n\n### 修改原因\n1. 理由。"
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("标记原文", issues)

    def test_inline_markers_count_as_marker_section(self):
        """含内联标记 + 修改原因时格式合格（内联标记即标记原文）"""
        report = "正文【1|错|对】\n\n### 修改原因\n1. 理由。"
        ok, issues = _enforce_format(report)
        self.assertTrue(ok, f"内联标记报告应合格: {issues}")
        self.assertNotIn("标记原文", issues)

    def test_missing_reason_section(self):
        report = "### 标记原文\n内容【1|错|对】"
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("修改原因", issues)

    def test_marker_number_missing_in_reasons(self):
        """标记 1、2 但原因只有 1 → 报缺失"""
        report = ("### 标记原文\n内容【1|错|对】【2|错|对】\n\n"
                  "### 修改原因\n1. 理由一。")
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("2", issues)

    def test_extra_reason_number(self):
        """原因 2 没有对应标记 → 报多余"""
        report = ("### 标记原文\n内容【1|错|对】\n\n"
                  "### 修改原因\n1. 理由一。\n2. 多余的理由。")
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("2", issues)

    def test_malformed_marker(self):
        """畸形标记【13 后缺 | → 报格式异常"""
        report = "### 标记原文\n内容【13 这里没有竖线\n\n### 修改原因\n1. 理由。"
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("格式异常", issues)

    def test_two_digit_marker_not_misjudged(self):
        """【13|...】 不得被 【1 误判为畸形标记"""
        report = ("### 标记原文\n内容【13|错|对】\n\n"
                  "### 修改原因\n13. 理由。")
        ok, issues = _enforce_format(report)
        self.assertTrue(ok, f"两位数标记不应误报: {issues}")

    def test_internal_heading_in_marker_section(self):
        """标记原文内含内部 ### 标题（前置参考）时边界正确"""
        report = ("### 标记原文\n"
                  "正文【1|错|对】\n\n"
                  "### 权威原文\n前置参考内容\n\n"
                  "### 修改原因\n1. 理由。")
        ok, issues = _enforce_format(report)
        self.assertTrue(ok, f"内部标题不应破坏边界: {issues}")

    def test_empty_input(self):
        ok, issues = _enforce_format("")
        self.assertFalse(ok)


class TestEnforceAndFix(unittest.TestCase):
    """enforce_and_fix 成败分支（mock LLM 修正，验证编排逻辑）"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="tdd_fmt_")
        self.file_path = os.path.join(self.tmpdir, "_校对报告.md")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_report_skips_fix(self):
        """格式合格时直接返回原文，不触发修正"""
        with mock.patch("core.format_enforcement._bash_format_fix") as fix:
            final, was_fixed, issues = enforce_and_fix(
                self.file_path, OK_REPORT, "http://x", "k", "m")
        self.assertEqual(final, OK_REPORT)
        self.assertFalse(was_fixed)
        fix.assert_not_called()

    def test_fix_success_returns_fixed(self):
        """修正成功（且重验通过）返回修正后内容"""
        bad = "只有正文没有结构"
        fixed = OK_REPORT
        with mock.patch("core.format_enforcement._bash_format_fix", return_value=fixed):
            final, was_fixed, issues = enforce_and_fix(
                self.file_path, bad, "http://x", "k", "m")
        self.assertEqual(final, fixed)
        self.assertTrue(was_fixed)

    def test_fix_failure_falls_back_to_original(self):
        """修正失败或重验不过时回退原始内容"""
        bad = "只有正文没有结构"
        with mock.patch("core.format_enforcement._bash_format_fix", return_value=None):
            final, was_fixed, issues = enforce_and_fix(
                self.file_path, bad, "http://x", "k", "m")
        self.assertEqual(final, bad)
        self.assertFalse(was_fixed)
        self.assertTrue(issues)

    def test_fix_unverifiable_falls_back(self):
        """修正后仍不合格（重验失败）也回退原始"""
        bad = "只有正文没有结构"
        with mock.patch("core.format_enforcement._bash_format_fix",
                        return_value="还是不规范的输出"):
            final, was_fixed, _ = enforce_and_fix(
                self.file_path, bad, "http://x", "k", "m")
        self.assertEqual(final, bad)
        self.assertFalse(was_fixed)


class TestMarkerInsideFormula(unittest.TestCase):
    """标记位于 $...$ 公式内部的格式检查（提示词已禁止，程序校验兜底）。"""

    def test_marker_inside_formula_detected(self):
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "安培力做功大小为$\\frac{{B}^{2}{L}^{2}【1|$v$|$v_0$】x}{R+r}$\n\n"
            "### 修改原因\n1. 符号统一。\n"
        )
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("公式内部", issues)

    def test_marker_wrapping_formula_passes(self):
        """标记包裹整个公式 → 合规，不报公式内部问题"""
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "总电动势为【1|$E=BLv$|$E_1=BLv_1$】，方向不变\n\n"
            "### 修改原因\n1. 符号统一。\n"
        )
        ok, issues = _enforce_format(report)
        self.assertTrue(ok, f"包裹公式的标记应合规: {issues}")
        self.assertNotIn("公式内部", issues)

    def test_normal_markers_with_math_pass(self):
        """正文含公式但标记在公式外 → 合规"""
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "由$E=BLv$得【1|导体棒|金属棒】运动速度\n\n"
            "### 修改原因\n1. 术语统一。\n"
        )
        ok, issues = _enforce_format(report)
        self.assertTrue(ok, f"公式外标记应合规: {issues}")

    def test_marker_field_with_dollar_inside_formula_detected(self):
        """标记字段内含 $（【1|aaa$|bbb$】）位于公式内：仍应识别为公式内部"""
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "安培力做功大小为$\\frac{【1|aaa$|bbb$】x}{R+r}$\n\n"
            "### 修改原因\n1. 修正。\n"
        )
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("公式内部", issues)

    def test_marker_with_dollar_outside_formula_passes(self):
        """标记在公式外但字段内含 $：不得误报为公式内部"""
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "电阻【1|aaa$|bbb$】阻值，由$E=BLv$得\n\n"
            "### 修改原因\n1. 修正。\n"
        )
        ok, issues = _enforce_format(report)
        self.assertTrue(ok, f"公式外标记不应报公式内部: {issues}")
        self.assertNotIn("公式内部", issues)

    def test_unpaired_dollar_detected(self):
        """行内 $ 数量为奇数（配对失败）→ 报格式问题"""
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "由$E=BLv得【1|导体棒|金属棒】速度\n\n"
            "### 修改原因\n1. 术语统一。\n"
        )
        ok, issues = _enforce_format(report)
        self.assertFalse(ok)
        self.assertIn("美元符号未配对", issues)

    def test_escaped_dollar_not_counted_as_unpaired(self):
        """\\$ 转义美元不参与配对计数"""
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "价格\\$5【1|a|b】，由$E=BLv$得\n\n"
            "### 修改原因\n1. 修正。\n"
        )
        ok, issues = _enforce_format(report)
        self.assertTrue(ok, f"转义美元不应误报未配对: {issues}")
        self.assertNotIn("美元符号未配对", issues)

    def test_even_dollars_across_marker_passes(self):
        """标记字段内嵌完整公式（$...$ 成对）→ $ 配对正常，不误报"""
        report = (
            "一般问题\n\n### 标记原文\n编号：第1题\n内容：\n"
            "电动势【1|$E=BLv$|$E_1=BLv_1$】，方向不变\n\n"
            "### 修改原因\n1. 符号统一。\n"
        )
        ok, issues = _enforce_format(report)
        # $ 偶数不报未配对；标记在公式外（字段内公式屏蔽后）也不报公式内部
        self.assertNotIn("美元符号未配对", issues)
        self.assertNotIn("公式内部", issues)


if __name__ == "__main__":
    unittest.main()
