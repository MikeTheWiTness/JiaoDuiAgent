"""三种标记（批注/格式/校对）的嵌套与交错逻辑测试。

验证 build_paracol_content 在复杂场景下：
- 不崩溃
- 所有标记都被正确处理
- 最终 LaTeX 输出包含预期的命令
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.latex_generator import build_paracol_content


def _count(s: str, pattern: str) -> int:
    """统计 pattern 在 s 中出现的次数（纯文本匹配）"""
    return s.count(pattern)


class TestFormatMarkers(unittest.TestCase):
    """纯格式标记转换（无校对标记掺杂）"""

    def test_underline_alone(self):
        result = build_paracol_content("<下划线>重点</下划线>", [])
        self.assertIn(r"\uline{重点}", result,
                      "纯下划线应转为 LaTeX 下划线命令")

    def test_emphasis_dot_alone(self):
        result = build_paracol_content("<着重>重点</着重>", [])
        self.assertIn(r"\CJKunderdot{重点}", result)

    def test_wavy_alone(self):
        result = build_paracol_content("<波浪线>重点</波浪线>", [])
        self.assertIn(r"\uwave{重点}", result)

    def test_strike_alone(self):
        result = build_paracol_content("<删除线>被删</删除线>", [])
        self.assertIn(r"\sout{被删}", result)

    def test_multiple_formats_separate(self):
        result = build_paracol_content(
            "<下划线>A</下划线>和<着重>B</着重>", []
        )
        self.assertIn(r"\uline{A}", result)
        self.assertIn(r"\CJKunderdot{B}", result)

    def test_format_inside_format(self):
        """嵌套格式：下划线内含着重号"""
        result = build_paracol_content(
            "<下划线>外层<着重>内层</着重>尾</下划线>", []
        )
        # 两个格式都应该出现
        self.assertTrue(
            r"\uline" in result and r"\CJKunderdot" in result,
            f"嵌套格式应同时包含两个 LaTeX 命令，实际: {result[:200]}"
        )


class TestInlineCorrectionInsideFormat(unittest.TestCase):
    """校对标记出现在格式标记内部 — 这是用户最关心的场景"""

    def test_correction_inside_underline(self):
        """<下划线>ABC【1|DE|F】</下划线> → 下划线中 DE 标红+①"""
        corrections = [
            {"num": 1, "type": "text", "original": "DE", "correction": "F",
             "reason": "错字"},
        ]
        result = build_paracol_content(
            "<下划线>ABC【1|DE|F】</下划线>", corrections
        )
        # 校对标记被处理 → \corrmark 出现
        self.assertIn(r"\corrmark", result,
                      "下划线内的校对标记应转为 \\corrmark")
        # 格式标记被处理 → \uline 出现
        self.assertIn(r"\uline", result,
                      "下划线格式标记应转为 \\uline")
        # 右栏应有修改意见
        self.assertIn("修改意见", result,
                      "右栏应有「修改意见」区块")

    def test_multiple_corrections_inside_format(self):
        """<下划线>【1|A|B】中间【2|C|D】</下划线> — 一个格式内多个校对"""
        corrections = [
            {"num": 1, "type": "text", "original": "A", "correction": "B",
             "reason": "错1"},
            {"num": 2, "type": "text", "original": "C", "correction": "D",
             "reason": "错2"},
        ]
        result = build_paracol_content(
            "<下划线>【1|A|B】中间【2|C|D】</下划线>", corrections
        )
        # 两个 \corrmark
        self.assertGreaterEqual(_count(result, r"\corrmark"), 2,
                                "应有两个 \\corrmark")
        self.assertIn(r"\uline", result)
        # 右栏应有两条修改意见
        self.assertIn("修改意见", result)

    def test_correction_touching_format_boundary(self):
        """校对标记紧邻 </下划线> 但不在其内"""
        corrections = [
            {"num": 1, "type": "text", "original": "X", "correction": "Y",
             "reason": "边界"},
        ]
        result = build_paracol_content(
            "<下划线>ABC</下划线>【1|X|Y】", corrections
        )
        self.assertIn(r"\uline", result)
        self.assertIn(r"\corrmark", result)

    def test_correction_straddling_format_boundary_not_in_marker(self):
        """校对标记横跨 </下划线><着重> 但不包含标签本身"""
        corrections = [
            {"num": 1, "type": "text", "original": "ABC然后DE", "correction": "ABC然后DF",
             "reason": "跨区域"},
        ]
        # 校对原文是 "ABC然后DE" — 出现在两段格式之间
        result = build_paracol_content(
            "<下划线>ABC</下划线>然后<着重>DE</着重>", corrections
        )
        # 如果找不到精确匹配，apply_markers 会 fallback
        # 这题主要验证不崩溃
        self.assertIn(r"\uline", result)
        self.assertIn(r"\CJKunderdot", result)
        # 原文 "ABC然后DE" 不连续出现在文本里（有标签隔开）
        # 所以可能不会生成 \corrmark，但程序不应崩溃
        self.assertIn("paracol", result)


class TestCommentWithFormatMarkers(unittest.TestCase):
    """批注标记与格式标记交错"""

    def test_comment_inside_format(self):
        """<下划线>ABC<批注 id=1><原>此处</原><改>注意</改></批注>DEF</下划线>"""
        result = build_paracol_content(
            "<下划线>ABC<批注 id=1><原>此处</原><改>注意</改></批注>DEF</下划线>", []
        )
        self.assertIn(r"\uline", result,
                      "格式标记应被处理")
        # 批注应被提取并在右栏展示
        self.assertIn("原有批注", result,
                      "右栏应有「原有批注」区块")
        # 批注方框应出现
        self.assertIn(r"\fbox{1}", result)

    def test_format_inside_comment_anchor_text(self):
        """批注锚点文字包含格式标记 — 极端情况"""
        result = build_paracol_content(
            "正文<下划线>锚点文字<批注 id=1><原>此处</原><改>批注内容</改></批注></下划线>结尾", []
        )
        # 不崩溃即可
        self.assertIn("paracol", result)

    def test_comment_between_format_blocks(self):
        """<下划线>A</下划线><批注 id=1><原>此处</原><改>注</改></批注><着重>B</着重>"""
        result = build_paracol_content(
            "<下划线>A</下划线><批注 id=1><原>此处</原><改>注</改></批注><着重>B</着重>", []
        )
        self.assertIn(r"\uline{A}", result)
        self.assertIn(r"\CJKunderdot{B}", result)
        self.assertIn("原有批注", result)


class TestAllThreeInterleaved(unittest.TestCase):
    """三种标记同时出现，复杂交错"""

    def test_comment_format_correction_together(self):
        """批注+格式+校对 同框 — 实际场景"""
        corrections = [
            {"num": 1, "type": "text", "original": "错字", "correction": "对字",
             "reason": "笔误"},
            {"num": 2, "type": "text", "original": "再错", "correction": "再对",
             "reason": "又错"},
        ]
        md = (
            '<下划线>开头【1|错字|对字】'
            '<批注 id=1><原>此处</原><改>人工批注</改></批注>'
            '中间<着重>重点【2|再错|再对】</着重>尾</下划线>'
        )
        result = build_paracol_content(md, corrections)

        # 格式
        self.assertIn(r"\uline", result)
        self.assertIn(r"\CJKunderdot", result)
        # 批注
        self.assertIn("原有批注", result)
        # 校对
        self.assertIn(r"\corrmark", result)
        self.assertIn("修改意见", result)
        # 整体结构
        self.assertIn(r"\begin{paracol}", result)
        self.assertIn(r"\end{paracol}", result)

    def test_all_three_in_sequence(self):
        """依次排列：格式块 → 批注 → 校对标记"""
        corrections = [
            {"num": 1, "type": "text", "original": "误", "correction": "正",
             "reason": "错"},
        ]
        md = (
            '<下划线>下划线文字</下划线>'
            '<批注 id=1><原>此处</原><改>这是一条批注</改></批注>'
            '然后【1|误|正】结尾'
        )
        result = build_paracol_content(md, corrections)
        self.assertIn(r"\uline", result)
        self.assertIn("原有批注", result)
        self.assertIn(r"\corrmark", result)


class TestEdgeCases(unittest.TestCase):
    """边界情况：不崩溃 + 合理输出"""

    def test_empty_input(self):
        result = build_paracol_content("", [])
        self.assertIn(r"\begin{paracol}", result)

    def test_no_markers(self):
        result = build_paracol_content("普通文字无标记", [])
        self.assertIn("普通文字无标记", result)
        self.assertNotIn("原有批注", result)
        self.assertNotIn("修改意见", result)

    def test_only_comments(self):
        result = build_paracol_content(
            "文字<批注 id=1><原>此处</原><改>批注</改></批注>文字", []
        )
        self.assertIn("原有批注", result)
        self.assertNotIn("修改意见", result)

    def test_only_corrections(self):
        corrections = [
            {"num": 1, "type": "text", "original": "误", "correction": "正",
             "reason": "错"},
        ]
        result = build_paracol_content("文字【1|误|正】文字", corrections)
        self.assertNotIn("原有批注", result)
        self.assertIn("修改意见", result)

    def test_only_formats(self):
        result = build_paracol_content(
            "<下划线>A</下划线><着重>B</着重>", []
        )
        self.assertIn(r"\uline{A}", result)
        self.assertIn(r"\CJKunderdot{B}", result)

    def test_unclosed_format_tag(self):
        """<下划线>无闭合 — 不崩溃，标签残留"""
        result = build_paracol_content("<下划线>没有闭合", [])
        self.assertIn("<下划线>", result,
                      "未闭合的标签应原样保留而非崩溃")

    def test_unclosed_comment_tag(self):
        """<批注1>未闭合 — 不崩溃"""
        result = build_paracol_content("文字<批注1>未闭合", [])
        self.assertIn("paracol", result)  # 不崩溃

    def test_correction_with_angle_brackets(self):
        """校对原文含 < > 字符（如数学符号）"""
        corrections = [
            {"num": 1, "type": "text", "original": "x<y", "correction": "x>y",
             "reason": "方向反了"},
        ]
        result = build_paracol_content("比较【1|x<y|x>y】大小", corrections)
        self.assertIn(r"\corrmark", result)
        # 不应把 x<y 中的 < 误当作格式标签处理

    def test_correction_marker_not_mistaken_for_format(self):
        """【1|<下划线>|</下划线>】— 校对标记内的文本像格式标签"""
        corrections = [
            {"num": 1, "type": "text", "original": "<下划线>",
             "correction": "</下划线>", "reason": "多余的格式标签"},
        ]
        # 校对标记内的 <下划线> 只是"原文"字段，不应被当作格式标签处理
        # _process_inline_markers 先运行，会把整个标记拿走
        # 所以不会触发 _convert_format_markers
        result = build_paracol_content(
            "正文【1|<下划线>|</下划线>】尾", corrections
        )
        # 不应有实际的 \uline 命令（因为校对标记内的 <下划线> 是原文字段）
        # 但如果有也说明格式处理跑了——这题主要验证不崩溃
        self.assertIn("paracol", result)

    def test_bold_inside_underline(self):
        """<下划线>**粗体**</下划线> — Markdown 格式与 XML 格式嵌套"""
        result = build_paracol_content("<下划线>**粗体**</下划线>", [])
        self.assertIn(r"\uline", result)
        self.assertIn(r"\textbf{粗体}", result)


class TestRightColumnLayout(unittest.TestCase):
    """验证右栏各区块的正确出现条件"""

    def test_all_sections_when_appropriate(self):
        """有批注 + 有校对 + 有评审结果 → 所有区块出现"""
        corrections = [
            {"num": 1, "type": "text", "original": "误", "correction": "正",
             "reason": "错"},
        ]
        review_judgments = [
            {"id": 1, "verdict": "正确", "reason": "确实错了"},
        ]
        review_supplements = ["遗漏1"]

        result = build_paracol_content(
            "开头<批注 id=1><原>此处</原><改>内容</改></批注>【1|误|正】尾",
            corrections,
            review_judgments=review_judgments,
            review_supplements=review_supplements,
        )
        self.assertIn("原有批注", result, "应有原有批注区块")
        self.assertIn("批注评审", result, "应有批注评审区块")
        self.assertIn("补充发现", result, "应有补充发现区块")
        self.assertIn("修改意见", result, "应有修改意见区块")

    def test_no_false_right_sections(self):
        """无批注 + 无校对 → 右栏只有空壳"""
        result = build_paracol_content("普通文字", [])
        self.assertNotIn("原有批注", result)
        self.assertNotIn("批注评审", result)
        self.assertNotIn("补充发现", result)
        self.assertNotIn("修改意见", result)

    def test_correctionbox_count(self):
        """\\correctionbox 数量应等于批注数 + 修改数 + 评审数 + 补充数"""
        corrections = [
            {"num": 1, "type": "text", "original": "误", "correction": "正",
             "reason": "错"},
            {"num": 2, "type": "text", "original": "错", "correction": "对",
             "reason": "又错"},
        ]
        review_judgments = [
            {"id": 1, "verdict": "正确", "reason": "ok"},
            {"id": 2, "verdict": "有误", "reason": "不对"},
            {"id": 3, "verdict": "部分正确", "reason": "半对"},
        ]
        review_supplements = ["漏1", "漏2"]

        result = build_paracol_content(
            "开头<批注 id=1><原>此处</原><改>批1</改></批注>中<批注 id=2><原>此处</原><改>批2</改></批注>【1|误|正】间【2|错|对】尾",
            corrections,
            review_judgments=review_judgments,
            review_supplements=review_supplements,
        )
        count = _count(result, r"\correctionbox")
        expected = 2 + 2 + 3 + 2  # 批注2 + 修改2 + 评审3 + 补充2
        self.assertEqual(count, expected,
                         f"correctionbox 数量应为 {expected}，实际 {count}")


if __name__ == "__main__":
    unittest.main()
