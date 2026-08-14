"""测试 core/defaults.py 的 comprehensive_clean 函数

重点验证：
1. 数学公式保护与恢复（$...$ 和 $$...$$）
2. 碎片化公式不产生 MATH 占位符残留（regression test）
3. 连公式场景正确处理
4. 嵌套/相邻数学块保护
5. 表格管道符清理
"""

import os
import sys

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
        r"""公式中的特殊字符（^、_、{、}、\）应保留"""
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
        assert '\x00' not in result, "残留空字节"
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

    # ---- 表格边框行清理（带序号前缀） ----

    def test_table_border_with_pandoc_ordered_list_prefix(self):
        """Pandoc 转义序号前缀的表格边框行应被移除：1\\.  +---+"""
        input_text = (
            "1\\.  +----------------------------------+"
            "--------------------------------------------------------------------"
            "---------------------------------------------------------------+\n"
            "答案：  B\n"
            "解答：  这是解答内容。\n"
            "2\\.  +----------------------------------+"
            "--------------------------------------------------------------------"
            "---------------------------------------------------------------+\n"
            "解答：  第二题解答。"
        )
        result = comprehensive_clean(input_text)
        # 边框行应被移除
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '答案：  B' in result
        assert '解答：  这是解答内容' in result
        assert '解答：  第二题解答' in result

    def test_table_border_with_plain_ordered_list_prefix(self):
        """普通序号前缀的表格边框行应被移除：1. +---+"""
        input_text = (
            "1. +-------+--------+\n"
            "答案：  A\n"
            "解答：  内容。"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '答案：  A' in result

    def test_table_border_with_multi_digit_prefix(self):
        """多位序号前缀的表格边框行应被移除：12\\.  +---+"""
        input_text = (
            "12\\.  +-----+-----+\n"
            "内容行"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '内容行' in result

    def test_table_border_line_only_removed_not_content(self):
        """仅移除表格边框行，保留前面的内容行"""
        input_text = (
            "1\\.  +-----------+\n"
            "这是一条正常内容。\n"
            "2\\.  +-----------+\n"
            "这也是正常内容。"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '这是一条正常内容' in result
        assert '这也是正常内容' in result

    def test_nested_table_border_with_prefix(self):
        """嵌套表格中的边框行：| | 1\\.  | +---+ → 应被跳过"""
        input_text = (
            "| 前面内容 | 列2 |\n"
            "| | 1\\.                               | +----------------------------------+------------------------+\n"
            "| | 选项A                             | 内容A                            |\n"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留嵌套表格边框: {result}"
        assert '选项A' in result
        assert '内容A' in result

    def test_nested_table_border_multi_prefix(self):
        """嵌套表格中多个序号边框行均被跳过"""
        input_text = (
            "| | 1\\.  | +-----+-----+\n"
            "| | 选项 | 内容 |\n"
            "| | 2\\.  | +-----+-----+\n"
            "| | 答案 | 结果 |\n"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留边框: {result}"

    # ---- 纯 - 分隔线清理（无 + 或 |） ----

    def test_pure_dash_separator_removed(self):
        """纯 - 分隔线（无 + 或 |）应被移除"""
        input_text = (
            "前面内容。\n"
            "-----------------------------------------------------------------------\n"
            "后面内容。"
        )
        result = comprehensive_clean(input_text)
        assert '---' not in result, f"残留分隔线: {result}"
        assert '前面内容' in result
        assert '后面内容' in result

    def test_dash_space_mixed_separator_removed(self):
        """- 和空格混合的分隔线应被移除（如 Pandoc 表格残留）"""
        input_text = (
            "前面。\n"
            "----------------- ---------------------------------------- -----------------\n"
            "后面。"
        )
        result = comprehensive_clean(input_text)
        assert '---' not in result, f"残留分隔线: {result}"
        assert '前面' in result
        assert '后面' in result

    def test_long_dash_separator_removed(self):
        """超长纯 - 分隔线应被移除"""
        input_text = (
            "开头。\n"
            + "-" * 120 + "\n"
            "结尾。"
        )
        result = comprehensive_clean(input_text)
        assert '---' not in result, f"残留分隔线: {result}"
        assert '开头' in result
        assert '结尾' in result

    def test_ellipsis_preserved(self):
        """纯省略号行（...）应保留不被误删"""
        input_text = (
            "前面内容。\n"
            "...\n"
            "后面内容。"
        )
        result = comprehensive_clean(input_text)
        assert '...' in result, f"省略号被误删: {result}"

    def test_multiple_ellipsis_preserved(self):
        """长省略号行（......）应保留"""
        input_text = "前面。\n..........\n后面。"
        result = comprehensive_clean(input_text)
        assert '....' in result, f"省略号被误删: {result}"


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


# ============================================================
# 出题意图清理（clean_intent_markers）
# ============================================================

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.defaults import clean_intent_markers


class TestIntentMarkerCleanup:
    """清理【出题意图】段落"""

    def test_basic_intent_with_xiaoshiniudao(self):
        """【出题意图】→ **小试牛刀1**：删除意图保留题目"""
        input_text = (
            "前面的内容。\n\n"
            "【出题意图】\n"
            "**小试牛刀1**（2016·甘肃平凉市一模）\n"
            "阅读下面的宋词。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result, f"出题意图残留: {result}"
        assert '**小试牛刀1**' in result
        assert '前面的内容' in result
        assert '阅读下面的宋词' in result

    def test_intent_with_inline_text(self):
        """【出题意图】意象自身特点... → **小试牛刀2**"""
        input_text = (
            "上文。\n\n"
            "【出题意图】意象自身特点：\"浮云\"这一意象，一般含有人物漂泊之意。\n"
            "**小试牛刀2**（2025・湖南高三月考卷）\n"
            "阅读下面的诗歌。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**小试牛刀2**' in result
        assert '上文' in result
        assert '阅读下面的诗歌' in result

    def test_intent_with_li_pattern(self):
        """【出题意图】→ **例1**"""
        input_text = (
            "内容。\n\n"
            "【出题意图】\n"
            "**例1**（2020・北京卷）\n"
            "阅读下面的诗歌。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**例1**' in result
        assert '阅读下面的诗歌' in result

    def test_intent_with_lian_pattern(self):
        """【出题意图】→ **练1**"""
        input_text = (
            "内容。\n\n"
            "【出题意图】这里有一些说明文字。\n"
            "**练1**\n"
            "题目内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**练1**' in result
        assert '题目内容' in result

    def test_multiple_intent_sections(self):
        """多个【出题意图】段全部清理"""
        input_text = (
            "开头。\n\n"
            "【出题意图】第一段意图说明。\n"
            "**小试牛刀1**\n"
            "第一题内容。\n\n"
            "中间内容。\n\n"
            "【出题意图】第二段意图说明。\n"
            "**例1**\n"
            "第二题内容。\n\n"
            "结尾。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**小试牛刀1**' in result
        assert '**例1**' in result
        assert '开头' in result
        assert '第一题内容' in result
        assert '中间内容' in result
        assert '第二题内容' in result
        assert '结尾' in result

    def test_intent_without_following_marker_preserved(self):
        """【出题意图】后无题目编号 → 保留不删"""
        input_text = (
            "前面。\n\n"
            "【出题意图】这里没有后续题目编号。\n"
            "这是一段普通内容。\n\n"
            "结尾。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' in result
        assert '这是一段普通内容' in result

    def test_intent_at_end_of_file(self):
        """【出题意图】在文件末尾，无后续内容 → 保留"""
        input_text = "前面内容。\n\n【出题意图】最后的意图说明。"
        result = clean_intent_markers(input_text)
        assert '【出题意图】' in result

    def test_real_world_case_from_raw(self):
        """真实 raw.md 片段：意图+解题步骤+模板 → 题目"""
        input_text = (
            "解题步骤\n"
            "步骤一：明确答题角度\n"
            "在拿到题目后，先准确审题。\n"
            "步骤二：三步作答\n"
            "（1）翻译/提炼诗句意思\n"
            "抓住主要意象，结合全诗。\n"
            "答题模板\n"
            "（1）这首诗描绘出一幅……的画面或景象。\n\n"
            "【出题意图】先给**选择题**让学生进行判断。从江水、北斗星和高城等意象来看，空间上组成的是辽阔高远的意境。\n"
            "**小试牛刀4**（2024・新课标Ⅱ）\n"
            "阅读下面的诗歌，完成后面的题目。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**小试牛刀4**' in result
        assert '解题步骤' in result
        assert '答题模板' in result
        assert '阅读下面的诗歌' in result

    def test_intent_with_blank_lines_before_marker(self):
        """【出题意图】和题目编号之间有空行 → 正确清理"""
        input_text = (
            "前面。\n\n"
            "【出题意图】说明文字。\n"
            "\n"
            "**例5**（2018·天津卷）\n"
            "题目内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**例5**' in result
        assert '题目内容' in result

    # ---- 灵活匹配（标签可在同行、后可跟来源信息） ----

    def test_intent_same_line_as_label(self):
        """【出题意图】和标签在同一行 → 清理到标签前"""
        input_text = (
            "前面。\n\n"
            "【出题意图】意图说明。**小试牛刀1**\n"
            "题目内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result, f"残留: {result}"
        assert '**小试牛刀1**' in result
        assert '题目内容' in result

    def test_label_with_source_info(self):
        """标签后有来源信息（如 '（2026·山东青岛模拟）'）→ 正常匹配"""
        input_text = (
            "前面。\n\n"
            "【出题意图】说明。\n"
            "**例1**（2026·山东青岛模拟）\n"
            "题目内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**例1**（2026·山东青岛模拟）' in result
        assert '题目内容' in result

    def test_label_with_source_info_same_line(self):
        """同行标签 + 来源信息 → 正常匹配"""
        input_text = (
            "前面。\n\n"
            "【出题意图】说明。**教师版**（2026秋·通用版）\n"
            "内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**教师版**（2026秋·通用版）' in result

    def test_intent_between_multiple_labels(self):
        """意图在多标签之间，只删除到第一个匹配的标签"""
        input_text = (
            "**一本班1**\n"
            "一本班内容。\n\n"
            "【出题意图】意图说明。\n"
            "**例1**内容。\n\n"
            "**一本班2**\n"
            "更多内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        # 第一个标签 **例1** 保留（作为停止点）
        assert '**例1**' in result
        # 前面的标签不受影响
        assert '**一本班1**' in result
        assert '**一本班2**' in result

    # ---- 分层/班型标签标志 ----

    def test_intent_with_yibenban_marker(self):
        """【出题意图】→ **一本班1**"""
        input_text = (
            "前面。\n\n"
            "【出题意图】一本班说明。\n"
            "**一本班1**\n"
            "分层内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**一本班1**' in result

    def test_intent_with_shuangyiliu_marker(self):
        """【出题意图】→ **双一流班2**"""
        input_text = (
            "前面。\n\n"
            "【出题意图】双一流班说明。\n"
            "**双一流班2**\n"
            "分层内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**双一流班2**' in result

    def test_intent_with_qingbeiban_marker(self):
        """【出题意图】→ **清北班1**"""
        input_text = (
            "前面。\n\n"
            "【出题意图】清北班说明。\n"
            "**清北班1**\n"
            "分层内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**清北班1**' in result

    def test_intent_with_jiaoshiban_marker(self):
        """【出题意图】→ **教师版**（无数字后缀）"""
        input_text = (
            "前面。\n\n"
            "【出题意图】教师版说明。\n"
            "**教师版**\n"
            "内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**教师版**' in result

    def test_intent_with_yibenban_jiaoshi_marker(self):
        """【出题意图】→ **一本班教师版**"""
        input_text = (
            "前面。\n\n"
            "【出题意图】一本班教师版说明。\n"
            "**一本班教师版**\n"
            "内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**一本班教师版**' in result

    def test_intent_with_qingbeiban_jiaoshi_marker(self):
        """【出题意图】→ **清北班教师版**"""
        input_text = (
            "前面。\n\n"
            "【出题意图】清北班教师版说明。\n"
            "**清北班教师版**\n"
            "内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**清北班教师版**' in result

    # ---- 自定义标志覆盖 ----

    def test_custom_markers_override(self):
        """通过参数传入自定义标志列表，绕过默认常量"""
        input_text = (
            "前面。\n\n"
            "【出题意图】说明。\n"
            "**自定义题型A**\n"
            "题目内容。"
        )
        # 用默认标志不应匹配
        result_default = clean_intent_markers(input_text)
        assert '【出题意图】' in result_default, "默认标志不应匹配自定义题型"

        # 用自定义标志应匹配
        result_custom = clean_intent_markers(input_text, problem_markers=[r'自定义题型[A-Z]'])
        assert '【出题意图】' not in result_custom
        assert '**自定义题型A**' in result_custom

    # ---- 通用 + 学科覆盖合并 ----

    def test_get_intent_problem_markers_default_only(self):
        """无 config 时返回纯默认常量"""
        from core.defaults import DEFAULT_INTENT_PROBLEM_MARKERS, get_intent_problem_markers
        result = get_intent_problem_markers(config=None)
        assert result == DEFAULT_INTENT_PROBLEM_MARKERS

    def test_get_intent_problem_markers_merges_config(self):
        """config 中的独有标志（如 真题\\d+）追加到默认列表后面"""
        from core.defaults import get_intent_problem_markers
        config = {"lecture_wrapped_patterns": [r"真题\d+", r"例\d+"]}
        result = get_intent_problem_markers(config=config)
        # 真题\d+ 不在默认中，应由 config 追加
        assert r"真题\d+" in result
        # 去重验证：例\d+ 已在默认中，只出现一次
        assert result.count(r"例\d+") == 1

    def test_merge_then_clean_with_config_markers(self):
        """合并后执行清理：config 独有的 真题\\d+ 标志应生效"""
        from core.defaults import get_intent_problem_markers
        config = {"lecture_wrapped_patterns": [r"真题\d+"]}
        markers = get_intent_problem_markers(config=config)

        input_text = (
            "前面。\n\n"
            "【出题意图】真题说明。\n"
            "**真题1**（2024・全国卷）\n"
            "题目内容。"
        )
        result = clean_intent_markers(input_text, problem_markers=markers)
        assert '【出题意图】' not in result
        assert '**真题1**' in result

    # ---- 通用层新增标志覆盖 ----

    def test_intent_with_Aban_marker(self):
        """【出题意图】→ **A班1**"""
        input_text = (
            "前面。\n\n"
            "【出题意图】A班说明。\n"
            "**A班1**\n"
            "分层内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**A班1**' in result

    def test_intent_with_APlus_ban_marker(self):
        """【出题意图】→ **A+班1**（含正则特殊字符 +）"""
        input_text = (
            "前面。\n\n"
            "【出题意图】A+班说明。\n"
            "**A+班1**\n"
            "分层内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**A+班1**' in result

    def test_intent_with_Sban_marker(self):
        """【出题意图】→ **S班1**"""
        input_text = (
            "前面。\n\n"
            "【出题意图】S班说明。\n"
            "**S班1**\n"
            "分层内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**S班1**' in result

    def test_intent_with_yibenban_li_marker(self):
        """【出题意图】→ **一本班例题**（无数字后缀）"""
        input_text = (
            "前面。\n\n"
            "【出题意图】一本班例题说明。\n"
            "**一本班例题**\n"
            "内容。"
        )
        result = clean_intent_markers(input_text)
        assert '【出题意图】' not in result
        assert '**一本班例题**' in result

    def test_custom_markers_extend_default(self):
        """通过参数扩展默认标志（额外添加学科特有标志）"""
        input_text = (
            "前面。\n\n"
            "【出题意图】说明。\n"
            "**【例题精讲1】**\n"
            "题目内容。"
        )
        # 默认标志不包含【例题精讲】，应保留
        result_default = clean_intent_markers(input_text)
        assert '【出题意图】' in result_default

        # 扩展标志后应匹配
        from core.defaults import DEFAULT_INTENT_PROBLEM_MARKERS
        extended = list(DEFAULT_INTENT_PROBLEM_MARKERS) + [r'【例题精讲\d+】']
        result_extended = clean_intent_markers(input_text, problem_markers=extended)
        assert '【出题意图】' not in result_extended
        assert '**【例题精讲1】**' in result_extended
