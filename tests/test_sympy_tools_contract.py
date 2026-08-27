"""sympy 工具链行为合约测试（批修复 P1/P2/P5/P6/P7/P9/P10）。

锁定这批修复的行为：符号白名单防劫持、check_equality 浮点容差、
退化输入报错、无穷/复数序列化形态、plan 状态机、工具参数校验、独立解题入参校验。
全部通过工具实例实调（走 sandbox 子进程）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.sympy_tools.tools import (
    CheckEqualityTool,
    CircleFromTwoPointsTool,
    EvaluateExpressionTool,
    GeometryTool,
    SolvePhysicsFormulaTool,
    VectorOperationsTool,
)
from shared.plan_tools import PlanUpdateTool
from shared.physics_tools import IndependentSolveTool


# ---- P1：白名单符号防劫持 ----


def test_symbols_not_hijacked_by_sympy_global():
    """I/S/alpha/beta/gamma 等应作为普通 Symbol 解析，不再是虚数单位/函数/注册器。"""
    assert json.loads(EvaluateExpressionTool()._run("alpha*beta"))["result"] == "alpha*beta"
    assert json.loads(EvaluateExpressionTool()._run("S*3"))["result"] == "3*S"
    assert json.loads(EvaluateExpressionTool()._run("I**2"))["result"] == "I**2"  # Symbol 而非 -1


def test_pi_still_constant():
    """pi 保留圆周率常数语义（物理公式需要 2*pi*f 之类的常数）。"""
    r = json.loads(EvaluateExpressionTool()._run("2*pi"))
    assert r["success"] is True
    assert abs(r["result"] - 6.28318530718) < 1e-9


def test_formula_solve_current_I():
    """P1 自愈：I = B*L*v/(R+r) 解现 I——此前因 I 被解析为虚数单位必返回 null。"""
    r = json.loads(SolvePhysicsFormulaTool()._run(
        formula="I = B*L*v/(R+r)", solve_for="I"))
    assert r["success"] is True
    assert r["result"] is not None
    assert "B" in r["result"] and "v" in r["result"]


def test_formula_solve_F_with_values():
    """F = B*I*L 代入求值——此前返回字符串 "I"（虚数未替换）。"""
    r = json.loads(SolvePhysicsFormulaTool()._run(
        formula="F = B*I*L", solve_for="F",
        known_values={"B": 1, "I": 2.5, "L": 1}))
    assert r["success"] is True
    assert r["result"] == 2.5


def test_geometry_still_works():
    """几何模板回归：白名单改造不能破坏 Point/Line 解析。"""
    r = json.loads(GeometryTool()._run(
        "Line(Point(0,0), Point(1,1)).angle_between(Line(Point(0,0), Point(1,0)))"))
    assert r["success"] is True
    assert abs(r["result"] - 0.785398163397) < 1e-6


# ---- P2：浮点容差 ----


def test_equality_float_tolerance():
    """0.1+0.2 与 0.3 应判相等（此前浮点误差判 false，导致误标）。"""
    r = json.loads(CheckEqualityTool()._run("0.1+0.2", "0.3"))
    assert r["success"] is True
    assert r["result"] is True


def test_equality_still_detects_inequality():
    r = json.loads(CheckEqualityTool()._run("0.3", "0.4"))
    assert r["result"] is False


def test_equality_trig_identity():
    r = json.loads(CheckEqualityTool()._run("sin(x)**2 + cos(x)**2", "1"))
    assert r["result"] is True


# ---- P9：退化输入 ----


def test_angle_zero_vector_rejected():
    r = json.loads(VectorOperationsTool()._run(
        operation="angle", vec_a=[1, 0], vec_b=[0, 0]))
    assert r["success"] is False
    assert "零向量" in r["error"]


def test_projection_zero_vector_rejected():
    r = json.loads(VectorOperationsTool()._run(
        operation="projection", vec_a=[1, 0], vec_b=[0, 0]))
    assert r["success"] is False


def test_circle_same_points_rejected():
    r = json.loads(CircleFromTwoPointsTool()._run(
        entry_point=["0", "0"], velocity_direction=[1, 0],
        impact_point=["0", "0"], impact_normal=[0, 1]))
    assert r["success"] is False
    assert "重合" in r["error"]


def test_circle_zero_direction_rejected():
    r = json.loads(CircleFromTwoPointsTool()._run(
        entry_point=["0", "0"], velocity_direction=[0, 0],
        impact_point=["0", "2"], impact_normal=[0, 1]))
    assert r["success"] is False


# ---- P10：序列化分支 ----


def test_division_by_zero_marked():
    r = json.loads(EvaluateExpressionTool()._run("1/0"))
    assert r["success"] is True
    assert "未定义" in r["result"]


def test_sqrt_negative_one_complex_form():
    r = json.loads(EvaluateExpressionTool()._run("sqrt(-1)"))
    assert r["success"] is True
    assert r["result"] == "0+1i"


# ---- P5：plan_update 状态机 ----


def test_plan_update_rejects_no_in_progress_with_pending():
    t = PlanUpdateTool(nudge_template="")
    todos = [
        {"content": "第一步", "status": "completed"},
        {"content": "第二步", "status": "pending"},
    ]
    r = t._run(todos)
    assert r["ok"] is False


def test_plan_update_rejects_invalid_status():
    t = PlanUpdateTool(nudge_template="")
    todos = [
        {"content": "第一步", "status": "done"},
    ]
    r = t._run(todos)
    assert r["ok"] is False
    assert "非法状态" in r["summary"]


def test_plan_update_all_completed_still_ok():
    t = PlanUpdateTool(nudge_template="")
    todos = [{"content": "第一步", "status": "completed"}]
    r = t._run(todos)
    assert r["ok"] is True


# ---- P6：参数校验（直接走 execute_tool 前的校验路径）----


def test_execute_tool_bad_argument_shape():
    """错误参数类型返回统一中文错误（含工具名），不再裸 traceback。"""
    from core.api_client import execute_tool

    out = execute_tool(
        [EvaluateExpressionTool()], "evaluate_expression", {"expression": 123})
    assert "evaluate_expression" in out
    assert "参数错误" in out


# ---- P7：independent_solve 入参校验 ----


def test_independent_solve_short_question_rejected():
    r = json.loads(IndependentSolveTool()._run(
        question_without_answer="太短", solve_prompt="请独立求解"))
    assert r["ok"] is False
    assert "过短" in r["error"]


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
