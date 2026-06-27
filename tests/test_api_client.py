"""测试 call_api 核心改造：StopReason、压缩历史、返回值扩展"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api_client import (
    StopReason,
    _compress_history,
    _is_empty_or_duplicate,
    tool_to_openai,
    execute_tool,
)


class TestStopReason(unittest.TestCase):
    """验证 StopReason 枚举值"""

    def test_stop_reason_values(self):
        self.assertEqual(StopReason.END_TURN, "end_turn")
        self.assertEqual(StopReason.TOOL_LOOP, "tool_loop")
        self.assertEqual(StopReason.MAX_TURNS, "max_turns")
        self.assertEqual(StopReason.ERROR, "error")


class TestCompressHistory(unittest.TestCase):
    """验证对话历史压缩逻辑"""

    def test_compression_removes_tool_messages(self):
        messages = [
            {"role": "system", "content": "你是校对 agent"},
            {"role": "user", "content": "校对这道题"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "function": {"name": "web_fetch", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "[搜索结果为空]"},
            {"role": "assistant", "content": "最终结果"},
        ]

        compressed = _compress_history(messages, 1)

        roles = [m["role"] for m in compressed]
        self.assertIn("system", roles)
        self.assertIn("user", roles)
        self.assertTrue(any("【系统提示】" in m.get("content", "") for m in compressed))

    def test_compression_preserves_text_assistant(self):
        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "题目"},
            {"role": "assistant", "content": "## 校对计划\n1. 通读全文"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "function": {"name": "x"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "empty"},
        ]

        compressed = _compress_history(messages, 1)
        self.assertTrue(any("校对计划" in m.get("content", "") for m in compressed))

    def test_compression_with_zero_tool_calls(self):
        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "题目"},
        ]

        compressed = _compress_history(messages, 0)
        self.assertTrue(any("0 次" in m.get("content", "") for m in compressed))


class TestIsEmptyOrDuplicate(unittest.TestCase):
    """验证连续空结果检测逻辑"""

    def test_empty_result_detected(self):
        self.assertTrue(_is_empty_or_duplicate("", []))
        self.assertTrue(_is_empty_or_duplicate("   ", []))

    def test_empty_marker_detected(self):
        self.assertTrue(_is_empty_or_duplicate("[搜索结果为空]: 未找到", []))
        self.assertTrue(_is_empty_or_duplicate("[网页抓取失败]: timeout", []))
        self.assertTrue(_is_empty_or_duplicate("[识典古籍未收录]", []))
        self.assertTrue(_is_empty_or_duplicate("[搜韵网未收录此内容]", []))
        self.assertTrue(_is_empty_or_duplicate("[网页内容为空]", []))
        self.assertTrue(_is_empty_or_duplicate("未知工具: fake_tool", []))

    def test_valid_result_not_detected(self):
        self.assertFalse(_is_empty_or_duplicate("有效的搜索结果文本", []))

    def test_duplicate_detected(self):
        recent = ["result A", "result B"]
        self.assertTrue(_is_empty_or_duplicate("result A", recent))

    def test_unique_result_not_duplicate(self):
        recent = ["result A", "result B"]
        self.assertFalse(_is_empty_or_duplicate("result C", recent))


if __name__ == "__main__":
    unittest.main()
