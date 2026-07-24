"""测试 PlanUpdateTool：校对计划管理工具"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.plan_tools import PlanItem, PlanUpdateTool


class TestPlanUpdateTool(unittest.TestCase):
    """验证 PlanUpdateTool 的核心行为"""

    def setUp(self):
        self.tool = PlanUpdateTool()

    def test_basic_plan_creation(self):
        todos = [
            {"content": "通读全文，识别文本类型", "status": "in_progress", "activeForm": "正在通读全文"},
            {"content": "逐题校对答案", "status": "pending", "activeForm": "逐题校对中"},
            {"content": "自检格式", "status": "pending", "activeForm": "自检格式中"},
        ]
        result = self.tool._run(todos)
        self.assertTrue(result["ok"])
        self.assertIn("共 3 项", result["summary"])

    def test_complete_plan_triggers_nudge(self):
        todos = [
            {"content": "通读全文", "status": "completed", "activeForm": "通读全文"},
            {"content": "逐题校对", "status": "completed", "activeForm": "逐题校对"},
            {"content": "自检格式", "status": "completed", "activeForm": "自检格式"},
        ]
        result = self.tool._run(todos)
        self.assertTrue(result["ok"])
        self.assertIn("所有校对步骤已完成", result["nudge"])

    def test_two_items_all_done_no_nudge(self):
        todos = [
            {"content": "校对答案", "status": "completed", "activeForm": "校对答案"},
            {"content": "自检格式", "status": "completed", "activeForm": "自检格式"},
        ]
        result = self.tool._run(todos)
        self.assertTrue(result["ok"])
        self.assertEqual(result["nudge"], "")

    def test_multiple_in_progress_rejected(self):
        todos = [
            {"content": "通读全文", "status": "in_progress", "activeForm": "通读全文"},
            {"content": "逐题校对", "status": "in_progress", "activeForm": "逐题校对"},
            {"content": "自检格式", "status": "pending", "activeForm": "自检格式"},
        ]
        result = self.tool._run(todos)
        self.assertFalse(result["ok"])
        self.assertIn("应该恰好 1 项", result["summary"])

    def test_step_transition(self):
        todos = [
            {"content": "通读全文", "status": "completed", "activeForm": "通读全文"},
            {"content": "逐题校对", "status": "in_progress", "activeForm": "逐题校对"},
            {"content": "自检格式", "status": "pending", "activeForm": "自检格式"},
        ]
        result = self.tool._run(todos)
        self.assertTrue(result["ok"])
        self.assertIn("逐题校对", result["summary"])

    def test_tool_schema_valid(self):
        from core.api_client import tool_to_openai
        schema = tool_to_openai(self.tool)
        self.assertEqual(schema["function"]["name"], "plan_update")
        self.assertIn("todos", schema["function"]["parameters"]["properties"])

    def test_empty_list_ok(self):
        result = self.tool._run([])
        self.assertTrue(result["ok"])

    def test_plan_item_validation(self):
        item = PlanItem(content="校对答案", status="pending", activeForm="校对答案…")
        self.assertEqual(item.content, "校对答案")
        self.assertEqual(item.status, "pending")

    def test_partial_complete_no_nudge(self):
        todos = [
            {"content": "通读全文", "status": "completed", "activeForm": "通读全文"},
            {"content": "逐题校对", "status": "completed", "activeForm": "逐题校对"},
            {"content": "自检格式", "status": "pending", "activeForm": "自检格式"},
        ]
        result = self.tool._run(todos)
        self.assertTrue(result["ok"])
        self.assertEqual(result["nudge"], "")


if __name__ == "__main__":
    unittest.main()
