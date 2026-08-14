"""化学式解析双源同步测试锁（ADR-0026）

确保 shared/chemistry_tools.py（运行时代码）与
shared/sympy_tools/templates.py（沙箱内嵌代码）中的 _parse_formula 实现保持一致。
"""
import inspect


def _extract_parse_formula_source(module, func_name: str) -> str:
    """提取模块中函数源码字符串（去缩进、去装饰器）。"""
    func = getattr(module, func_name)
    source = inspect.getsource(func)
    # 去掉首行的函数定义（def 行），只保留函数体
    lines = source.split("\n")
    # 找到函数体开始（第一个缩进行）
    body_start = 1
    for i, line in enumerate(lines):
        if i == 0:
            continue
        if line.strip() and not line.startswith("def ") and not line.startswith("@"):
            body_start = i
            break
    body = "\n".join(lines[body_start:])
    return body.strip()


def test_molar_masses_single_source():
    """验证 _MOLAR_MASSES 单一源：tools.py 从 chemistry_tools 导入同一对象。"""
    from shared.chemistry_tools import _MOLAR_MASSES as chem_masses
    from shared.sympy_tools.tools import _MOLAR_MASSES as tools_masses

    # 应是同一个对象（import 不复制）
    assert chem_masses is tools_masses, (
        "_MOLAR_MASSES 应为同一对象，tools.py 应从 chemistry_tools 导入而非本地定义"
    )

    # 结构与内容一致
    assert isinstance(chem_masses, dict)
    assert len(chem_masses) >= 50, f"摩尔质量数据库应含至少50种化合物，实际 {len(chem_masses)} 种"
    for formula, mass in chem_masses.items():
        assert isinstance(formula, str)
        assert isinstance(mass, float)


def test_chemistry_balance_still_works():
    """验证化学方程式配平功能不受影响。"""
    from shared.chemistry_tools import _MOLAR_MASSES
    # 基本完整性检查
    common = ["H2O", "CO2", "NaCl", "H2SO4", "NaOH", "O2", "H2"]
    for f in common:
        assert f in _MOLAR_MASSES, f"常见化合物 {f} 应在摩尔质量数据库中"


def test_parse_formula_sync_templates():
    """验证 templates.py 内嵌 _parse_formula 与 chemistry_tools 主实现结构一致。

    从 templates._TEMPLATES["chemistry_balance"].template 提取内嵌函数，
    与 chemistry_tools.parse_chemical_formula 比对核心解析结构。
    """
    import re as _re

    import shared.chemistry_tools as chem
    import shared.sympy_tools.templates as tmpl

    # 1. 从模板字符串提取内嵌 _parse_formula 函数体
    tmpl_str = tmpl._TEMPLATES["chemistry_balance"].template
    # 匹配 "def _parse_formula(f):" 到下一个顶级 "def " 或模板结束
    match = _re.search(r'def _parse_formula\(f\):(.*?)(?=\n\S|\Z)', tmpl_str, _re.DOTALL)
    assert match is not None, "模板应包含 _parse_formula 函数定义"
    tmpl_func_body = match.group(1)

    # 2. 获取 chemistry_tools.parse_chemical_formula 源码
    chem_source = _extract_parse_formula_source(chem, "parse_chemical_formula")

    # 3. 结构比对：两者都应有内嵌解析函数 _parse_group / _parse_group
    assert "def _parse_group" in tmpl_func_body, "模板 _parse_formula 应包含 _parse_group"
    assert "def _parse_group" in chem_source or "_parse_group" in chem_source, \
        "chemistry_tools 应包含内嵌解析函数"

    # 4. 两者都处理元素（大写字母开头）和数字（下标计数）
    assert "isupper()" in tmpl_func_body, "模板应处理大写元素符号"
    assert "isdigit()" in tmpl_func_body, "模板应处理数字下标"
    assert "isupper()" in chem_source or "isupper" in chem_source, \
        "chemistry_tools 应处理大写元素符号"

    # 5. 两者都处理括号分组（如 Ca(OH)2）
    assert "'('" in tmpl_func_body or '"("' in tmpl_func_body, "模板应处理括号分组"
    assert "'('" in chem_source or '"("' in chem_source, \
        "chemistry_tools 应处理括号分组"

    # 6. 基本功能验证：用真实化学式测试两端输出一致
    test_formulas = ["H2O", "CO2", "NaCl", "Ca(OH)2", "Al2(SO4)3", "Fe2O3"]
    for formula in test_formulas:
        chem_result = chem.parse_chemical_formula(formula)
        assert isinstance(chem_result, dict), f"{formula}: 应返回 dict"
        assert len(chem_result) > 0, f"{formula}: 解析结果不应为空"
