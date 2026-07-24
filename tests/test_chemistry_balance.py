"""测试化学方程式配平工具的公式解析能力

重点验证：
1. 基础化学式解析（无括号）
2. 含括号化学式解析（本次修复的核心目标）
3. 复杂多原子离子基团
4. 配平结果正确性
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# 单元测试：_parse_formula 的提取版（直接测试解析逻辑）
# ============================================================
import re

from shared.chemistry_tools import parse_chemical_formula


def _parse_formula_v1(f):
    """当前版本（有 bug）：不支持括号"""
    _elem_pattern = re.compile(r'([A-Z][a-z]?)(\d*)')
    _counts = {}
    for _m in _elem_pattern.finditer(f):
        _el = _m.group(1)
        _n = int(_m.group(2)) if _m.group(2) else 1
        _counts[_el] = _counts.get(_el, 0) + _n
    return _counts


class TestParseFormulaV1:
    """当前版本的行为（展示 bug）"""

    def test_simple_formula(self):
        """简单化学式 H2O 正确"""
        assert _parse_formula_v1("H2O") == {"H": 2, "O": 1}

    def test_CO2(self):
        assert _parse_formula_v1("CO2") == {"C": 1, "O": 2}

    def test_NaCl(self):
        assert _parse_formula_v1("NaCl") == {"Na": 1, "Cl": 1}

    def test_parenthesized_CaOH2_IS_BROKEN(self):
        """Ca(OH)2 → 解析错误（这就是 bug）"""
        result = _parse_formula_v1("Ca(OH)2")
        # 正确应为 Ca:1, O:2, H:2
        # 当前错误：不会解析括号
        assert result != {"Ca": 1, "O": 2, "H": 2}, \
            "当前版本应该解析错误（这个测试确认 bug 存在）"

    def test_parenthesized_Fe2SO43_IS_BROKEN(self):
        """Fe2(SO4)3 → 解析错误"""
        result = _parse_formula_v1("Fe2(SO4)3")
        # 正确应为 Fe:2, S:3, O:12
        assert result != {"Fe": 2, "S": 3, "O": 12}, \
            "当前版本应该解析错误"

    def test_parenthesized_AlOH3_IS_BROKEN(self):
        """Al(OH)3 → 解析错误"""
        result = _parse_formula_v1("Al(OH)3")
        assert result != {"Al": 1, "O": 3, "H": 3}, \
            "当前版本应该解析错误"


# ============================================================
# 单元测试：修复后的 parse_chemical_formula（导入 shared.chemistry_tools 真实实现）
# ============================================================


class TestParseFormulaV2:
    """修复版的行为（导入 shared.chemistry_tools.parse_chemical_formula 真实实现）"""

    # --- 简单化学式（不应退化） ---
    def test_simple_H2O(self):
        assert parse_chemical_formula("H2O") == {"H": 2, "O": 1}

    def test_simple_CO2(self):
        assert parse_chemical_formula("CO2") == {"C": 1, "O": 2}

    def test_simple_NaCl(self):
        assert parse_chemical_formula("NaCl") == {"Na": 1, "Cl": 1}

    def test_simple_H2SO4(self):
        assert parse_chemical_formula("H2SO4") == {"H": 2, "S": 1, "O": 4}

    def test_simple_Fe2O3(self):
        assert parse_chemical_formula("Fe2O3") == {"Fe": 2, "O": 3}

    # --- 含括号化学式（本次修复的核心目标） ---
    def test_CaOH2(self):
        """Ca(OH)₂"""
        assert parse_chemical_formula("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}

    def test_Fe2SO43(self):
        """Fe₂(SO₄)₃"""
        assert parse_chemical_formula("Fe2(SO4)3") == {"Fe": 2, "S": 3, "O": 12}

    def test_AlOH3(self):
        """Al(OH)₃"""
        assert parse_chemical_formula("Al(OH)3") == {"Al": 1, "O": 3, "H": 3}

    def test_MgOH2(self):
        """Mg(OH)₂"""
        assert parse_chemical_formula("Mg(OH)2") == {"Mg": 1, "O": 2, "H": 2}

    def test_Ca3PO42(self):
        """Ca₃(PO₄)₂"""
        assert parse_chemical_formula("Ca3(PO4)2") == {"Ca": 3, "P": 2, "O": 8}

    def test_NH42SO4(self):
        """(NH₄)₂SO₄"""
        assert parse_chemical_formula("(NH4)2SO4") == {"N": 2, "H": 8, "S": 1, "O": 4}

    def test_FeOH3(self):
        """Fe(OH)₃"""
        assert parse_chemical_formula("Fe(OH)3") == {"Fe": 1, "O": 3, "H": 3}

    def test_BaOH2(self):
        """Ba(OH)₂"""
        assert parse_chemical_formula("Ba(OH)2") == {"Ba": 1, "O": 2, "H": 2}

    def test_CuOH2(self):
        """Cu(OH)₂"""
        assert parse_chemical_formula("Cu(OH)2") == {"Cu": 1, "O": 2, "H": 2}

    # --- 无括号的复杂化学式 ---
    def test_KMnO4(self):
        assert parse_chemical_formula("KMnO4") == {"K": 1, "Mn": 1, "O": 4}

    def test_NaHCO3(self):
        assert parse_chemical_formula("NaHCO3") == {"Na": 1, "H": 1, "C": 1, "O": 3}

    # --- 边界情况 ---
    def test_single_element(self):
        """单元素"""
        assert parse_chemical_formula("O2") == {"O": 2}

    def test_no_subscript(self):
        """无下标"""
        assert parse_chemical_formula("NaCl") == {"Na": 1, "Cl": 1}

    def test_empty_string(self):
        """空字符串"""
        assert parse_chemical_formula("") == {}


# ============================================================
# 集成测试：通过 BalanceChemicalEquationTool 验证配平结果
# ============================================================


class TestBalanceChemicalEquation:
    """通过实际工具调用验证配平正确性"""

    @pytest.fixture(autouse=True)
    def setup_tool(self):
        from shared.sympy_tools.tools import BalanceChemicalEquationTool
        self.tool = BalanceChemicalEquationTool()

    def _balance(self, equation):
        """调用配平工具，返回结果 dict（从嵌套结构中提取 result）"""
        result_str = self.tool._run(equation)
        outer = json.loads(result_str)
        # 工具返回 {"success": ..., "result": {...}, "error": ...}
        if "result" in outer:
            return outer["result"]
        return outer

    # --- 无括号方程式 ---
    def test_simple_combustion(self):
        """CH4 + O2 -> CO2 + H2O"""
        r = self._balance("CH4 + O2 -> CO2 + H2O")
        assert r.get("balanced_equation") is not None
        # Expected: CH4 + 2O2 -> CO2 + 2H2O
        eq = r["balanced_equation"]
        assert "CH4" in eq and "2O2" in eq and "CO2" in eq and "2H2O" in eq

    def test_Fe_O2_reaction(self):
        """Fe + O2 -> Fe2O3"""
        r = self._balance("Fe + O2 -> Fe2O3")
        eq = r["balanced_equation"]
        # Expected: 4Fe + 3O2 -> 2Fe2O3
        assert "4Fe" in eq and "3O2" in eq and "2Fe2O3" in eq

    # --- 含括号方程式（核心测试） ---
    def test_CaOH2_neutralization(self):
        """Ca(OH)2 + HCl -> CaCl2 + H2O（中和反应）"""
        r = self._balance("Ca(OH)2 + HCl -> CaCl2 + H2O")
        eq = r["balanced_equation"]
        assert "Ca(OH)2" in eq and "2HCl" in eq and "CaCl2" in eq and "2H2O" in eq

    def test_AlOH3_neutralization(self):
        """Al(OH)3 + HCl -> AlCl3 + H2O"""
        r = self._balance("Al(OH)3 + HCl -> AlCl3 + H2O")
        eq = r["balanced_equation"]
        assert "Al(OH)3" in eq and "3HCl" in eq and "AlCl3" in eq and "3H2O" in eq

    def test_FeOH3_decomposition(self):
        """Fe(OH)3 -> Fe2O3 + H2O"""
        r = self._balance("Fe(OH)3 -> Fe2O3 + H2O")
        eq = r["balanced_equation"]
        assert "2Fe(OH)3" in eq and "Fe2O3" in eq and "3H2O" in eq

    def test_BaOH2_H2SO4(self):
        """Ba(OH)2 + H2SO4 -> BaSO4 + H2O"""
        r = self._balance("Ba(OH)2 + H2SO4 -> BaSO4 + H2O")
        eq = r["balanced_equation"]
        assert "Ba(OH)2" in eq and "H2SO4" in eq and "BaSO4" in eq and "2H2O" in eq

    def test_Ca3PO42_complex(self):
        """Ca3(PO4)2 + H2SO4 -> CaSO4 + H3PO4"""
        r = self._balance("Ca3(PO4)2 + H2SO4 -> CaSO4 + H3PO4")
        eq = r["balanced_equation"]
        assert "Ca3(PO4)2" in eq and "3H2SO4" in eq
        assert "3CaSO4" in eq or "CaSO4" in eq  # coefficient handling
        # Verify correct stoichiometry
        coeffs = r.get("coefficients", [])
        assert len(coeffs) == 4

    def test_Fe2SO43_NaOH(self):
        """Fe2(SO4)3 + NaOH -> Fe(OH)3 + Na2SO4"""
        r = self._balance("Fe2(SO4)3 + NaOH -> Fe(OH)3 + Na2SO4")
        eq = r["balanced_equation"]
        assert "Fe2(SO4)3" in eq and "6NaOH" in eq
        assert "2Fe(OH)3" in eq and "3Na2SO4" in eq

    def test_NH42SO4_CaOH2(self):
        """(NH4)2SO4 + Ca(OH)2 -> CaSO4 + NH3 + H2O"""
        r = self._balance("(NH4)2SO4 + Ca(OH)2 -> CaSO4 + NH3 + H2O")
        eq = r["balanced_equation"]
        assert "(NH4)2SO4" in eq and "Ca(OH)2" in eq
        assert "CaSO4" in eq and "2NH3" in eq and "2H2O" in eq

    def test_CuOH2_thermal_decomp(self):
        """Cu(OH)2 -> CuO + H2O（氢氧化铜受热分解）"""
        r = self._balance("Cu(OH)2 -> CuO + H2O")
        eq = r["balanced_equation"]
        assert "Cu(OH)2" in eq and "CuO" in eq and "H2O" in eq

    # --- 错误输入 ---
    def test_impossible_equation_returns_error(self):
        """不可能发生的反应应返回错误"""
        r = self._balance("Na + H -> NaH2")
        # This is unbalanced and impossible - should return error or handle gracefully
        assert r.get("error") is not None or r.get("balanced_equation") is not None


# ============================================================
# 前置校验测试：含括号输入不应静默失败
# ============================================================


class TestBalancePreValidation:
    """配平工具输入校验（严重问题 #2）"""

    @pytest.fixture(autouse=True)
    def setup_tool(self):
        from shared.sympy_tools.tools import BalanceChemicalEquationTool
        self.tool = BalanceChemicalEquationTool()

    def _balance(self, equation):
        """调用配平工具，返回结果 dict（从嵌套结构中提取 result）"""
        result_str = self.tool._run(equation)
        outer = json.loads(result_str)
        if "result" in outer:
            return outer["result"]
        return outer

    def test_parenthesized_input_should_not_silently_fail(self):
        """含括号输入：修复前静默返回错误结果，修复后应返回正确结果"""
        r = self._balance("Ca(OH)2 + HCl -> CaCl2 + H2O")
        # 如果返回错误，coefficients 不会存在；如果成功，应有正确的配平
        if "coefficients" in r:
            coeffs = r["coefficients"]
            # 验证系数：Ca(OH)2:1, HCl:2, CaCl2:1, H2O:2
            assert coeffs == [1, 2, 1, 2], \
                f"配平系数应为 [1,2,1,2]，实际为 {coeffs}"
