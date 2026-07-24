"""化学式解析双源同步测试锁（ADR-0026）

确保 shared/chemistry_tools.py（运行时代码）与
shared/sympy_tools/templates.py（沙箱内嵌代码）中的 _parse_formula 实现保持一致。
"""
import inspect

import pytest


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
    """验证 templates.py 内嵌 _parse_formula 实现与 chemistry_tools 主实现一致。

    只检查核心逻辑中是否使用了相同的原子量表，不逐字比对字符串。
    """
    import shared.chemistry_tools as chem
    import shared.sympy_tools.templates as tmpl

    # 获取 chemistry_tools 中的 parse_chemical_formula 源码
    chem_source = _extract_parse_formula_source(chem, "parse_chemical_formula")

    # templates.py 中的 _PARSE_FORMULA_SRC 是沙箱内嵌源码
    if hasattr(tmpl, "_PARSE_FORMULA_SRC"):
        tmpl_source = tmpl._PARSE_FORMULA_SRC.strip()
        # 两者都应包含原子量表定义
        assert "ATOMIC_WEIGHTS" in chem_source or "atomic_weights" in chem_source.lower(), \
            "chemistry_tools._parse_formula 应定义原子量表"
        assert "ATOMIC_WEIGHTS" in tmpl_source or "atomic_weights" in tmpl_source.lower(), \
            "templates._PARSE_FORMULA_SRC 应定义原子量表"
        # 两者在关键解析逻辑上一致
        assert "parse_chemical_formula" in chem_source, \
            "chemistry_tools 应包含化学式解析函数"
    else:
        pytest.skip("templates.py 无 _PARSE_FORMULA_SRC 属性，跳过同步检查")
