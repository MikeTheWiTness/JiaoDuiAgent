#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""小学数学 v3.0 隔离测试 —— 不依赖 API、不跑 exe、不涉及多学科交叉。

覆盖：
  1. 模块导入与初始化
  2. 工具集构建（React / 非 React）
  3. 工具实际调用验证（sympy + geometry）
  4. 提示词生成与结构校验
  5. PlanUpdateTool nudge 置空验证
  6. 校对流程模拟（mock API）
  7. 标记格式规则自检

用法:
    python -X utf8 tests/test_math_v3_standalone.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 模块级导入检查 ──

def _import_subject_app():
    """动态加载小学数学 SubjectApp"""
    import importlib.util
    subject_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "subjects", "小学数学v3.0",
    )
    spec = importlib.util.spec_from_file_location(
        "_math", os.path.join(subject_dir, "subject.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, subject_dir


MathMod, MATH_DIR = _import_subject_app()
SubjectApp = MathMod.SubjectApp


# ═══════════════════════════════════════════════════════════════
# 1. 模块导入与初始化
# ═══════════════════════════════════════════════════════════════

class TestImportAndInit(unittest.TestCase):
    """验证模块可正常导入、SubjectApp 可实例化"""

    def test_subject_app_creates(self):
        app = SubjectApp(MATH_DIR)
        self.assertEqual(app.LEVEL, "小学")
        self.assertEqual(app.SUBJECT, "数学")
        self.assertEqual(app.name, "小学数学")
        self.assertEqual(app.version, "v3.0")
        self.assertFalse(app.react_mode)

    def test_config_loaded(self):
        app = SubjectApp(MATH_DIR)
        self.assertIn("question_prompt_lines", app.config)
        self.assertNotIn("knowledge_prompt_lines", app.config)
        # agent_prompt_lines 应该从 agent_prompt.json 加载
        self.assertIn("agent_prompt_lines", app.config)
        agent_lines = app.config["agent_prompt_lines"]
        self.assertGreater(len(agent_lines), 50, "agent_prompt 应至少 50 行")

    def test_config_has_split_rules(self):
        app = SubjectApp(MATH_DIR)
        self.assertIn("exam_question_pattern", app.config)


# ═══════════════════════════════════════════════════════════════
# 2. 工具集构建
# ═══════════════════════════════════════════════════════════════

class TestToolBuilding(unittest.TestCase):
    """验证非 React / React 两种模式下的工具集"""

    def setUp(self):
        self.app = SubjectApp(MATH_DIR)

    # ── 非 React 模式 ──

    def test_base_tool_count(self):
        tools = self.app.tools
        self.assertEqual(len(tools), 6, f"基础工具应为 6 个，实际 {len(tools)}")

    def test_base_tool_names(self):
        names = {t.name for t in self.app.tools}
        expected = {
            "evaluate_expression", "solve_equation", "check_equality",
            "simplify_expression", "geometry", "web_search",
        }
        self.assertEqual(names, expected)

    def test_base_no_react_tools(self):
        names = {t.name for t in self.app.tools}
        self.assertNotIn("plan_update", names)
        self.assertNotIn("independent_solve", names)
        self.assertNotIn("locate_paragraph", names)

    # ── React 模式 ──

    def test_react_tool_count(self):
        self.app.react_mode = True
        self.app.tools = self.app.build_tools()
        self.assertEqual(len(self.app.tools), 10, f"React 工具应为 10 个，实际 {len(self.app.tools)}")

    def test_react_tool_names(self):
        self.app.react_mode = True
        self.app.tools = self.app.build_tools()
        names = {t.name for t in self.app.tools}
        expected_base = {
            "evaluate_expression", "solve_equation", "check_equality",
            "simplify_expression", "geometry", "web_search",
        }
        expected_react = {
            "plan_update", "locate_paragraph", "read_section", "independent_solve",
        }
        self.assertTrue(expected_base.issubset(names), f"缺少基础工具: {expected_base - names}")
        self.assertTrue(expected_react.issubset(names), f"缺少 React 工具: {expected_react - names}")

    def test_plan_update_nudge_empty(self):
        """验证数学 PlanUpdateTool nudge 置空（对齐物理 ADR-0006 决策 2）"""
        self.app.react_mode = True
        self.app.tools = self.app.build_tools()
        plan_tool = next(t for t in self.app.tools if t.name == "plan_update")
        self.assertEqual(plan_tool.nudge_template, "",
                         "数学 PlanUpdateTool nudge 应为空字符串（自检靠 prompt 第 8 步）")

    def test_plan_update_nudge_suppressed(self):
        """全部 completed 时不输出 nudge（nudge_template=""）"""
        self.app.react_mode = True
        self.app.tools = self.app.build_tools()
        plan_tool = next(t for t in self.app.tools if t.name == "plan_update")
        todos = [
            {"content": "第1步：错词错字", "status": "completed", "activeForm": "检查错词错字"},
            {"content": "第2步：格式问题", "status": "completed", "activeForm": "检查格式"},
            {"content": "第3步：数字符号单位", "status": "completed", "activeForm": "检查符号"},
        ]
        result = plan_tool._run(todos)
        self.assertTrue(result["ok"])
        self.assertEqual(result["nudge"], "",
                         "nudge 应为空（nudge_template=\"\"）")


# ═══════════════════════════════════════════════════════════════
# 3. 工具实际调用验证
# ═══════════════════════════════════════════════════════════════

class TestToolExecution(unittest.TestCase):
    """验证每个 sympy/geometry 工具能正确处理小学数学典型输入"""

    @classmethod
    def setUpClass(cls):
        cls.app = SubjectApp(MATH_DIR)
        cls.app.react_mode = True
        cls.app.tools = cls.app.build_tools()

    def _get_tool(self, name):
        return next(t for t in self.app.tools if t.name == name)

    def _run_tool(self, name, **kwargs):
        tool = self._get_tool(name)
        raw = tool._run(**kwargs)
        return json.loads(raw)

    # ── evaluate_expression ──

    def test_eval_simple_arithmetic(self):
        r = self._run_tool("evaluate_expression", expression="2 + 3 * 4")
        self.assertTrue(r["success"])
        self.assertEqual(r["result"], 14)  # 不是 20

    def test_eval_with_substitutions(self):
        r = self._run_tool("evaluate_expression", expression="a + b",
                           substitutions={"a": 3.5, "b": 2.5})
        self.assertTrue(r["success"])
        self.assertEqual(r["result"], 6.0)

    def test_eval_fraction(self):
        r = self._run_tool("evaluate_expression", expression="2/3 + 1/6")
        self.assertTrue(r["success"])
        # 2/3 + 1/6 = 4/6 + 1/6 = 5/6 ≈ 0.8333...
        self.assertAlmostEqual(float(r["result"]), 5/6, places=5)

    # ── solve_equation ──

    def test_solve_linear(self):
        r = self._run_tool("solve_equation", equations=["2*x + 3 = 11"],
                           variables=["x"])
        self.assertTrue(r["success"], f"solve_equation 失败: {r}")
        # solve(dict=True) 返回 [{'x': 4.0}] 格式
        self.assertEqual(len(r["result"]), 1)
        self.assertAlmostEqual(r["result"][0]["x"], 4.0)

    def test_solve_proportion(self):
        """比例方程：3:4 = x:12 -> x=9"""
        r = self._run_tool("solve_equation", equations=["x/12 - 3/4"], variables=["x"])
        self.assertTrue(r["success"], f"solve_proportion 失败: {r}")
        self.assertAlmostEqual(r["result"][0]["x"], 9.0)

    # ── check_equality ──

    def test_check_equal(self):
        r = self._run_tool("check_equality",
                           expression_a="(x+1)**2", expression_b="x**2 + 2*x + 1")
        self.assertTrue(r["success"])
        self.assertTrue(r["result"])

    def test_check_not_equal(self):
        r = self._run_tool("check_equality",
                           expression_a="x + 1", expression_b="x - 1")
        self.assertTrue(r["success"])
        self.assertFalse(r["result"])

    # ── simplify_expression ──

    def test_simplify_fraction(self):
        r = self._run_tool("simplify_expression", expression="24/36")
        self.assertTrue(r["success"])
        # simplify 返回浮点数 2/3 ≈ 0.6667
        self.assertAlmostEqual(r["result"], 2/3, places=5,
                               msg=f"24/36 化简结果: {r['result']}")

    def test_expand(self):
        r = self._run_tool("simplify_expression", expression="(a+b)*(a-b)", method="expand")
        self.assertTrue(r["success"])
        self.assertIn("a**2 - b**2", str(r["result"]))

    # ── geometry ──

    def test_geometry_distance(self):
        """两点距离：直角三角形的斜边"""
        r = self._run_tool("geometry", expression="Point(0,0).distance(Point(3,4))")
        self.assertTrue(r["success"])
        self.assertEqual(r["result"], 5)

    def test_geometry_circle_intersection(self):
        """圆与水平线交点"""
        r = self._run_tool("geometry",
                           expression="Circle(Point(0,0), 5).intersection(Line(Point(-10,3), Point(10,3)))")
        self.assertTrue(r["success"])
        self.assertEqual(len(r["result"]), 2)

    def test_geometry_perpendicular_distance(self):
        """点到线的垂距"""
        r = self._run_tool("geometry",
                           expression="Line(Point(0,0), Point(1,0)).distance(Point(0,3))")
        self.assertTrue(r["success"])
        self.assertEqual(r["result"], 3)


# ═══════════════════════════════════════════════════════════════
# 4. 提示词生成与结构校验
# ═══════════════════════════════════════════════════════════════

class TestPromptGeneration(unittest.TestCase):
    """验证 get_question_prompt / get_tool_instructions"""

    @classmethod
    def setUpClass(cls):
        cls.app = SubjectApp(MATH_DIR)

    def test_question_prompt_non_react(self):
        """非 React 模式使用 config.json 的 question_prompt_lines"""
        self.app.react_mode = False
        prompt = self.app.get_question_prompt()
        self.assertIn("逐题五核校对", prompt)
        self.assertIn("evaluate_expression", prompt)

    def test_question_prompt_react(self):
        """React 模式使用 agent_prompt.json + 工具指令（三阶段结构）"""
        self.app.react_mode = True
        self.app.tools = self.app.build_tools()
        prompt = self.app.get_question_prompt()
        # 核心结构检查（ADR-0017 后改为预处理/主校对/输出三阶段）
        checks = [
            ("预处理阶段", "预处理阶段"),
            ("第 0 步：类型判定", "第 0 步"),
            ("主校对阶段", "主校对阶段"),
            ("第一阶段：通用检查", "第一阶段"),
            ("第二阶段：题目专项", "题目专项"),
            ("第二阶段：知识专项", "知识专项"),
            ("第三阶段：输出", "第三阶段"),
            ("反思机制", "反思"),
            ("格式自检", "格式自检"),
            ("强制返回格式", "强制返回格式"),
            ("independent_solve", "independent_solve"),
            ("geometry 工具", "geometry"),
            ("web_search", "web_search"),
            ("单位符号", "单位"),
        ]
        for label, keyword in checks:
            self.assertIn(keyword, prompt, f"React prompt 缺少: {label}")

    def test_tool_instructions_contains_sympy_section(self):
        self.app.react_mode = True
        self.app.tools = self.app.build_tools()
        instructions = self.app.get_tool_instructions()
        self.assertIn("符号计算与几何工具", instructions)
        self.assertIn("联网搜索工具", instructions)
        # 不应包含导航工具
        self.assertNotIn("plan_update", instructions)
        self.assertNotIn("locate_paragraph", instructions)

    def test_max_tool_loops(self):
        self.app.react_mode = False
        self.assertEqual(self.app.get_max_tool_loops(), 20)
        self.app.react_mode = True
        self.assertEqual(self.app.get_max_tool_loops(), 30)

    def test_prompt_no_leftover_physics_content(self):
        """确保数学 prompt 没有残留的物理内容"""
        self.app.react_mode = True
        self.app.tools = self.app.build_tools()
        prompt = self.app.get_question_prompt()
        forbidden = [
            "量纲分析", "dimensional_analysis",
            "solve_physics_formula", "vector_operations",
            "circle_from_two_points", "电磁场",
            "洛伦兹力", "运动学",
        ]
        for term in forbidden:
            self.assertNotIn(term, prompt,
                             f"数学 prompt 不应包含物理术语: {term}")


# ═══════════════════════════════════════════════════════════════
# 5. 校对流程模拟（不调用 API）
# ═══════════════════════════════════════════════════════════════

class TestProofreadPipeline(unittest.TestCase):
    """模拟校对完整流程中的关键步骤，不发送 API 请求"""

    @classmethod
    def setUpClass(cls):
        cls.app = SubjectApp(MATH_DIR)
        cls.app.react_mode = True
        cls.app.tools = cls.app.build_tools()

    def test_proofread_one_prompt_selection(self):
        """验证 proofread_one 在不同模式下选择正确的 prompt"""
        # 题目模式 → get_question_prompt
        prompt_q = self.app.get_question_prompt()
        self.assertIn("校对", prompt_q)

        # 批注评审模式 → get_review_prompt
        prompt_r = self.app.get_review_prompt()
        self.assertIn("校对", prompt_r)

    def test_tools_serializable_for_openai(self):
        """所有工具都能序列化为 OpenAI function calling 格式"""
        from core.api_client import tool_to_openai
        for tool in self.app.tools:
            try:
                schema = tool_to_openai(tool)
                self.assertIn("function", schema)
                self.assertIn("name", schema["function"])
                self.assertIn("parameters", schema["function"])
            except Exception as e:
                self.fail(f"工具 {tool.name} 序列化失败: {e}")

    def test_independent_solve_tool_schema(self):
        """验证 independent_solve 工具参数 schema 正确"""
        tool = next(t for t in self.app.tools if t.name == "independent_solve")
        schema = tool.args_schema.model_json_schema()
        props = schema["properties"]
        self.assertIn("question_without_answer", props)
        self.assertIn("solve_prompt", props)
        self.assertIn("original_answer", props)


# ═══════════════════════════════════════════════════════════════
# 6. 标记格式规则自检
# ═══════════════════════════════════════════════════════════════

class TestMarkupFormatRules(unittest.TestCase):
    """验证标记格式规则在 prompt 中完整且一致"""

    @classmethod
    def setUpClass(cls):
        cls.app = SubjectApp(MATH_DIR)
        cls.app.react_mode = True
        cls.app.tools = cls.app.build_tools()
        cls.prompt = cls.app.get_question_prompt()

    def test_markup_rules_present(self):
        rules = [
            "ASCII 数字",
            "无竖线",
            "不插入 $...$",
            "**...** 内部",
            "逐字一致",
            "每条标记对应一条原因",
        ]
        for rule in rules:
            self.assertIn(rule, self.prompt, f"标记规则缺失: {rule}")

    def test_output_format_structure(self):
        """输出格式包含总结行 + 标记原文 + 修改原因三段"""
        self.assertIn("总结行", self.prompt)
        self.assertIn("### 标记原文", self.prompt)
        self.assertIn("### 修改原因", self.prompt)

    def test_self_check_list(self):
        """第 8 步自检清单包含数学特有项（合并为紧凑格式）"""
        checks = [
            "标记数=原因数",
            "所有数值计算已调用 sympy 实算",
        ]
        for c in checks:
            self.assertIn(c, self.prompt, f"自检清单缺失: {c}")


# ═══════════════════════════════════════════════════════════════
# 7. 配置一致性检查
# ═══════════════════════════════════════════════════════════════

class TestConfigConsistency(unittest.TestCase):
    """验证 config.json 与 agent_prompt.json 之间无冲突"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(MATH_DIR, "config.json"), "r", encoding="utf-8") as f:
            cls.config = json.load(f)
        with open(os.path.join(MATH_DIR, "agent_prompt.json"), "r", encoding="utf-8") as f:
            cls.agent = json.load(f)

    def test_config_has_required_fields(self):
        self.assertIn("question_prompt_lines", self.config)
        # knowledge_prompt_lines 已从 schema 移除，不再出现在 config 中
        self.assertNotIn("knowledge_prompt_lines", self.config)
        self.assertIn("lecture_split", self.config)
        # exam_split 是可选的，默认值时不需写入

    def test_agent_prompt_is_valid_json(self):
        self.assertIn("agent_prompt_lines", self.agent)
        self.assertIsInstance(self.agent["agent_prompt_lines"], list)
        self.assertGreater(len(self.agent["agent_prompt_lines"]), 0)

    def test_no_broken_references(self):
        """agent_prompt 中引用的工具名都实际存在于工具集中"""
        app = SubjectApp(MATH_DIR)
        app.react_mode = True
        app.tools = app.build_tools()
        tool_names = {t.name for t in app.tools}

        agent_text = "\n".join(self.agent["agent_prompt_lines"])
        # 提取 `tool_name` 格式的引用
        import re
        backtick_refs = set(re.findall(r'`(\w+)`', agent_text))
        # 过滤掉非工具名的引用
        known_tools = {
            "plan_update", "locate_paragraph", "read_section",
            "evaluate_expression", "solve_equation", "check_equality",
            "simplify_expression", "geometry", "independent_solve",
            "web_search",
        }
        tool_refs = backtick_refs & known_tools
        for ref in tool_refs:
            self.assertIn(ref, tool_names,
                          f"agent_prompt 引用了不存在的工具: {ref}")

    def test_react_prompt_has_three_stage_structure(self):
        """验证 agent_prompt 采用预处理/主校对/输出三阶段结构（ADR-0017 后）"""
        agent_text = "\n".join(self.agent["agent_prompt_lines"])
        self.assertIn("预处理阶段", agent_text)
        self.assertIn("第 0 步", agent_text)
        self.assertIn("主校对阶段", agent_text)
        self.assertIn("第一阶段", agent_text)
        self.assertIn("第二阶段", agent_text)
        self.assertIn("第三阶段", agent_text)


# ═══════════════════════════════════════════════════════════════
# 8. UI 功能开关
# ═══════════════════════════════════════════════════════════════

class TestUIFeatures(unittest.TestCase):
    """验证 UI 功能开关保持不变"""

    def test_ui_features(self):
        app = SubjectApp(MATH_DIR)
        features = app.get_ui_features()
        self.assertFalse(features["show_knowledge_option"])
        self.assertTrue(features["show_pdf_option"])
        self.assertTrue(features["show_parallel_option"])
        self.assertIn("试卷", features["show_source_modes"])
        self.assertIn("自由校对", features["show_source_modes"])
        self.assertIn("批注评审", features["show_source_modes"])


if __name__ == "__main__":
    # 确保工作目录正确
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    unittest.main(verbosity=2)
