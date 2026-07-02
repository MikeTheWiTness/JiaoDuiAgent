# -*- coding: utf-8 -*-
"""测试 core/defaults.py 的 comprehensive_clean 函数

重点验证：
1. 数学公式保护与恢复（$...$ 和 $$...$$）
2. 碎片化公式不产生 MATH 占位符残留（regression test）
3. 连公式场景正确处理
4. 嵌套/相邻数学块保护
5. 表格管道符清理
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.defaults import comprehensive_clean


# ============================================================
# 基础功能
# ============================================================

class TestBasicMathProtection:
    """基础数学公式保护与恢复"""

    def test_inline_math_preserved(self):
        """内联公式 $...$ 不应被破坏"""
        assert comprehensive_clean(r"$a+b$") == r"$a+b$"

    def test_display_math_preserved(self):
        """显示公式 $$...$$ 不应被破坏"""
        assert comprehensive_clean(r"$$x^2+y^2=z^2$$") == r"$$x^2+y^2=z^2$$"

    def test_multiline_display_math(self):
        """多行显示公式应保留"""
        assert comprehensive_clean("$$\na + b = c\n$$") == "$$\na + b = c\n$$"

    def test_math_with_special_chars(self):
        """公式中的特殊字符（^、_、{、}、\）应保留"""
        assert comprehensive_clean(r"$x^{2} + y_{1} = z$") == r"$x^{2} + y_{1} = z$"

    def test_multiple_inline_math(self):
        """同一行多个内联公式"""
        assert comprehensive_clean(r"$a$ 和 $b$ 和 $c$") == r"$a$ 和 $b$ 和 $c$"

    def test_empty_input(self):
        """空输入"""
        assert comprehensive_clean("") == ""

    def test_no_math(self):
        """不含数学公式的纯文本"""
        assert comprehensive_clean("这是纯文本，没有公式。") == "这是纯文本，没有公式。"


# ============================================================
# 核心回归测试：碎片化公式（本次修复的目标 bug）
# ============================================================

class TestFragmentedMathRegression:
    """碎片化 $...$ 相邻 $$ 场景 —— 不应产生 MATH 占位符残留"""

    def test_chemistry_fragmented_C_option(self):
        r"""高中化学 C 选项碎片化公式：$\mathrm{C}$...$$=\!$$=\!$$=..."""
        # 这是本次 bug 的精确复现
        input_text = (
            r'$\mathrm{C}$．由反应'
            r'$\mathrm{S}{\mathrm{O}}_{3}^{2-}+{\mathrm{I}}_{2}+{\mathrm{H}}_{2}\mathrm{O}$'
            r'$$=\!$$=\!$$=\mathrm{S}{\mathrm{O}}_{4}^{2-}+2{\mathrm{I}}^{-}+2{\mathrm{H}}^{+}$'
            r'可知'
        )
        result = comprehensive_clean(input_text)
        # 绝不能包含 MATH 占位符残留
        assert 'MATH' not in result, f"残留 MATH 占位符: {result}"
        # 也不能包含 \x00 空字节
        assert '\x00' not in result, f"残留空字节"
        # 所有原始 $ 符号应存在（10 对 = 20 个 $）
        assert result.count('$') == input_text.count('$'), \
            f"$ 数量不匹配: 期望 {input_text.count('$')}, 实际 {result.count('$')}"
        # 关键内容应完整
        assert r'\mathrm{C}' in result
        assert r'\mathrm{S}{\mathrm{O}}_{3}^{2-}' in result
        assert r'\mathrm{S}{\mathrm{O}}_{4}^{2-}' in result

    def test_chemistry_fragmented_D_option(self):
        r"""高中化学 D 选项碎片化公式：$\mathrm{D}$...$$=\!$$=\!$$=..."""
        input_text = (
            r'$\mathrm{D}$．由反应'
            r'$\mathrm{S}{\mathrm{O}}_{3}^{2-}+2{\mathrm{S}}^{2-}+6{\mathrm{H}}^{+}$'
            r'$$=\!$$=\!$$=3\mathrm{S}\downarrow +3{\mathrm{H}}_{2}\mathrm{O}$'
            r'可知'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert r'\mathrm{D}' in result
        assert r'\downarrow' in result

    def test_three_consecutive_fragments(self):
        """三个连续的 $...$ 碎片与相邻 $$"""
        input_text = r'$A$$$B$$$C$$$D$'
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == r'$A$$$B$$$C$$$D$'

    def test_fragment_with_pipe_protection(self):
        """碎片化公式 + 管道符混合场景"""
        input_text = r'$|x|$$$=|y|$$'
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result


# ============================================================
# 连公式场景（原始用例，确保不回归）
# ============================================================

class TestConsecutiveMath:
    """连公式场景：$x=$$a+b$ 等"""

    def test_consecutive_inline(self):
        """两个内联公式相邻 $x=$$a+b$"""
        assert comprehensive_clean(r"$x=$$a+b$") == r"$x=$$a+b$"

    def test_three_consecutive_inline(self):
        """三个内联公式相邻"""
        assert comprehensive_clean(r"$a$$b$$c$") == r"$a$$b$$c$"

    def test_consecutive_mixed_with_text(self):
        """连公式中间夹文本"""
        assert comprehensive_clean(r"由$x=$$a+b$可知") == r"由$x=$$a+b$可知"

    def test_consecutive_with_subscripts(self):
        """连公式含上下标"""
        assert comprehensive_clean(r"$x^{2}$$=y_{1}$") == r"$x^{2}$$=y_{1}$"

    def test_consecutive_with_mathrm(self):
        r"""连公式含 \mathrm"""
        assert comprehensive_clean(r"$\mathrm{A}$$\mathrm{B}$") == r"$\mathrm{A}$$\mathrm{B}$"


# ============================================================
# 嵌套/内嵌场景
# ============================================================

class TestNestedMath:
    """嵌套数学块保护"""

    def test_display_math_containing_inline(self):
        """$$...$...$...$$ 显示公式内嵌内联公式"""
        input_text = r"$$x = $a+b$ + y$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text

    def test_display_math_containing_multiple_inline(self):
        """$$ 包含多个 $...$ 块"""
        input_text = r"$$f(x) = $a$ + $b$ \cdot x$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_inline_containing_dollar_text(self):
        r"""$...$ 中的 \$ 转义（边界情况，验证不会崩溃）"""
        input_text = r"$\$5.00$"
        result = comprehensive_clean(input_text)
        # 不崩溃即可，不严格要求 \$ 处理
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================
# 表格管道符清理
# ============================================================

class TestTablePipeCleanup:
    """表格 | 字符清理"""

    def test_pipe_removed_outside_math(self):
        """公式外的 | 应被移除"""
        result = comprehensive_clean(r"| 文本 | $a+b$ |")
        assert '|' not in result
        assert r"$a+b$" in result

    def test_pipe_preserved_inside_math(self):
        """公式内的 |（绝对值、集合）应保留"""
        # 绝对值
        result = comprehensive_clean(r"$|x|$ 和 $|y|$")
        assert r"$|x|$" in result
        assert r"$|y|$" in result

    def test_table_line_removed(self):
        """表格分隔行应被移除"""
        result = comprehensive_clean("| --- | --- |\n| a | b |")
        assert '---' not in result

    def test_table_with_math_and_pipes(self):
        """表格中有公式也有管道"""
        input_text = "| $\\alpha$ | $\\beta$ |\n| --- | --- |\n| $x$ | $y$ |"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_答案_line_merge(self):
        """'答案:' 行应与下一行合并"""
        input_text = "答案:\nB"
        result = comprehensive_clean(input_text)
        assert "答案: B" in result


# ============================================================
# 复杂综合场景
# ============================================================

class TestComplexScenarios:
    """复杂的综合场景"""

    def test_full_chemistry_answer_section(self):
        """完整的化学解答区域（含 A/B/C/D 四个选项的解答）"""
        input_text = (
            r'$\mathrm{A}$．由反应${\mathrm{S}}^{2-}+{\mathrm{I}}_{2}=\!=\!='
            r'\mathrm{S}\downarrow +2{\mathrm{I}}^{-}$可知，'
            r'还原剂${\mathrm{S}}^{2-}$的还原性大于还原产物${\mathrm{I}}^{-}$的还原性，'
            r'符合题意，可以发生，故$\mathrm{A}$不选；'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert r'\mathrm{A}' in result
        assert r'\downarrow' in result

    def test_latex_with_curly_braces(self):
        """多层花括号嵌套的 LaTeX"""
        input_text = r"${\mathrm{Fe(OH)}}_{3}$ 和 ${\mathrm{CaCO}}_{3}$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text

    def test_ion_charges(self):
        r"""离子电荷表示：${\mathrm{Fe}}^{2+}$、${\mathrm{SO}}_{4}^{2-}$"""
        input_text = r"${\mathrm{Fe}}^{2+}$ 和 ${\mathrm{SO}}_{4}^{2-}$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text

    def test_chemical_equation_with_conditions(self):
        """含反应条件的化学方程式"""
        input_text = (
            r'$2{\mathrm{H}}_{2}+{\mathrm{O}}_{2}'
            r'\xlongequal{\mathrm{点燃}}'
            r'2{\mathrm{H}}_{2}\mathrm{O}$'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_mixed_display_and_inline(self):
        """混合显示公式和内联公式"""
        input_text = (
            r'由$$E=mc^{2}$$可得$E$与$m$成正比。'
            r'又$$F=ma$$因此$a=F/m$。'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert r'$$E=mc^{2}$$' in result
        assert r'$$F=ma$$' in result
        assert r'$a=F/m$' in result

    def test_long_text_with_many_math_blocks(self):
        """长文本中散布大量数学块"""
        input_text = (
            r'已知$a>0$，$b>0$，且$a+b=1$，'
            r'求$\frac{1}{a}+\frac{1}{b}$的最小值。'
            r'由基本不等式$$x+y\geq 2\sqrt{xy}$$可得'
            r'$\frac{1}{a}+\frac{1}{b}\geq\frac{4}{a+b}=4$，'
            r'当且仅当$a=b=\frac{1}{2}$时取等。'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        # 关键内容完整
        assert r'$$x+y\geq 2\sqrt{xy}$$' in result
        assert r'\frac{1}{a}' in result

    def test_quadruple_dollar(self):
        """四个连续的 $：$$$$"""
        input_text = r"$$$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_double_dollar_adjacent_to_single(self):
        """$$ 后面紧跟 $"""
        input_text = r"$$x$$$y$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result


# ============================================================
# 边界情况
# ============================================================

class TestEdgeCases:
    """边界情况"""

    def test_unbalanced_math_is_untouched(self):
        """不配对的 $ 应保持原样（不崩溃）"""
        input_text = r"$a+b 没有闭合"
        result = comprehensive_clean(input_text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_only_dollar_signs(self):
        """纯 $ 符号"""
        result = comprehensive_clean("$$$")
        assert isinstance(result, str)

    def test_math_at_line_start(self):
        """行首的公式"""
        assert comprehensive_clean(r"$x$ 开头") == r"$x$ 开头"

    def test_math_at_line_end(self):
        """行尾的公式"""
        assert comprehensive_clean(r"结尾 $x$") == r"结尾 $x$"

    def test_single_dollar(self):
        """单个 $ 符号"""
        result = comprehensive_clean(r"价格 $5")
        assert isinstance(result, str)
        assert '$' in result or '5' in result  # 至少不崩溃

    def test_newlines_inside_math(self):
        """公式跨行（$...$ 内部不应跨行，但 $$ 可以）"""
        input_text = "$$\na\nb\n$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_chinese_and_math_mixed(self):
        """中文和数学公式混排"""
        input_text = r"根据公式$F=ma$，当$m=2\mathrm{kg}$时，$a=3\mathrm{m/s^{2}}$。"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text
