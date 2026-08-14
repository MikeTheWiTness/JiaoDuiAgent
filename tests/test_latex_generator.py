"""测试 shared/latex_generator 的转义与边界行为（回归锁定）。

覆盖：
- _escape_math_chars_outside_math 数学模式外下标/上标处理（修复：_{...} 后丢字符）
- 数学模式内内容原样保留
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.latex_generator import _escape_math_chars_outside_math, _restore_marked_newlines


class TestEscapeMathCharsOutsideMath(unittest.TestCase):
    """数学模式外裸 _ / ^ 的转义。

    回归：修复前 `_` 分支缺 continue，`_{...}` 闭合后的第一个字符被丢弃
    （'H_{2}O' → 'H$_{2}$'），修复后应保留。
    """

    def test_brace_subscript_keeps_following_char(self):
        """_{...} 后的字符必须保留（回归：H_{2}O 丢 O）"""
        self.assertEqual(_escape_math_chars_outside_math('H_{2}O'), 'H$_{2}$O')

    def test_brace_subscript_keeps_following_space(self):
        """_{...} 后的空格必须保留"""
        self.assertEqual(_escape_math_chars_outside_math('x_{n+1} end'), 'x$_{n+1}$ end')

    def test_brace_superscript_keeps_following_char(self):
        """^{...} 后的字符必须保留"""
        self.assertEqual(_escape_math_chars_outside_math('x^{2}y'), 'x$^{2}$y')

    def test_subscript_then_superscript_chemical_formula(self):
        """化学式 SO_{4}^{2-} 两个花括号组都保留"""
        self.assertEqual(_escape_math_chars_outside_math('SO_{4}^{2-}'), 'SO$_{4}$$^{2-}$')

    def test_multiple_subscripts(self):
        """连续多个 _{...} 组都保留"""
        self.assertEqual(_escape_math_chars_outside_math('a_{1}b_{2}c'), 'a$_{1}$b$_{2}$c')

    def test_unbraced_subscript_escaped(self):
        """无花括号的裸 _ 转义为 \\textunderscore{}，不丢字符"""
        self.assertEqual(_escape_math_chars_outside_math('a_b'), 'a\\textunderscore{}b')

    def test_math_mode_content_untouched(self):
        """数学模式 $...$ 内内容原样保留"""
        self.assertEqual(_escape_math_chars_outside_math('$H_{2}O$'), '$H_{2}O$')

    def test_plain_text_unchanged(self):
        """普通文本不受影响"""
        self.assertEqual(_escape_math_chars_outside_math('普通文本'), '普通文本')

    def test_empty_string(self):
        self.assertEqual(_escape_math_chars_outside_math(''), '')


class TestRestoreMarkedNewlines(unittest.TestCase):
    """marked_text 字面 \\n 还原为换行，同时保留 LaTeX 命令（P1-5）。

    回归：修复前用 str.replace('\\n', '\\n') 会把 \\noindent / \\newline 等
    命令中的 \\n 前缀一并替换，生成损坏 .tex。
    """

    def test_literal_newline_before_chinese_restored(self):
        self.assertEqual(
            _restore_marked_newlines(r'编号：第1题\n内容'),
            '编号：第1题\n内容')

    def test_literal_newline_before_digit_restored(self):
        self.assertEqual(
            _restore_marked_newlines(r'abc\n123'),
            'abc\n123')

    def test_literal_newline_before_punct_restored(self):
        self.assertEqual(
            _restore_marked_newlines(r'abc\n, def'),
            'abc\n, def')

    def test_noindent_command_preserved(self):
        self.assertEqual(
            _restore_marked_newlines(r'\noindent 段落'),
            r'\noindent 段落')

    def test_newline_command_preserved(self):
        self.assertEqual(
            _restore_marked_newlines(r'\newline 后'),
            r'\newline 后')

    def test_mixed_command_and_literal_newline(self):
        self.assertEqual(
            _restore_marked_newlines(r'\noindent\n正文'),
            r'\noindent' + '\n正文')


if __name__ == "__main__":
    unittest.main()
