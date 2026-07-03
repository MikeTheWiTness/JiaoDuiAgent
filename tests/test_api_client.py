"""测试 call_api 核心改造：StopReason、压缩历史、返回值扩展"""
import pytest
from core.api_client import (
    StopReason,
    _compress_history,
    _is_empty_or_duplicate,
    tool_to_openai,
    execute_tool,
)


class TestStopReason:
    """验证 StopReason 枚举值"""

    def test_stop_reason_values(self):
        assert StopReason.END_TURN == "end_turn"
        assert StopReason.TOOL_LOOP == "tool_loop"
        assert StopReason.MAX_TURNS == "max_turns"
        assert StopReason.ERROR == "error"


class TestCompressHistory:
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
        assert "system" in roles
        assert "user" in roles
        assert any("【系统提示】" in m.get("content", "") for m in compressed)

    def test_compression_preserves_text_assistant(self):
        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "题目"},
            {"role": "assistant", "content": "## 校对计划\n1. 通读全文"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "function": {"name": "x"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "empty"},
        ]

        compressed = _compress_history(messages, 1)
        assert any("校对计划" in m.get("content", "") for m in compressed)

    def test_compression_with_zero_tool_calls(self):
        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "user", "content": "题目"},
        ]

        compressed = _compress_history(messages, 0)
        assert any("0 次" in m.get("content", "") for m in compressed)


class TestIsEmptyOrDuplicate:
    """验证连续空结果检测逻辑"""

    def test_empty_result_detected(self):
        assert _is_empty_or_duplicate("", [])
        assert _is_empty_or_duplicate("   ", [])

    def test_empty_marker_detected(self):
        assert _is_empty_or_duplicate("[搜索结果为空]: 未找到", [])
        assert _is_empty_or_duplicate("[网页抓取失败]: timeout", [])
        assert _is_empty_or_duplicate("[识典古籍未收录]", [])
        assert _is_empty_or_duplicate("[搜韵网未收录此内容]", [])
        assert _is_empty_or_duplicate("[网页内容为空]", [])
        assert _is_empty_or_duplicate("未知工具: fake_tool", [])

    def test_valid_result_not_detected(self):
        assert not _is_empty_or_duplicate("有效的搜索结果文本", [])

    def test_duplicate_detected(self):
        recent = ["result A", "result B"]
        assert _is_empty_or_duplicate("result A", recent)

    def test_unique_result_not_duplicate(self):
        recent = ["result A", "result B"]
        assert not _is_empty_or_duplicate("result C", recent)

    def test_sympy_json_success_not_empty(self):
        """SymPy 工具返回的 JSON（含 "success" 字段）不应被判为空"""
        sympy_result = '{"success": true, "result": 0.4, "error": null, "code": "..."}'
        assert not _is_empty_or_duplicate(sympy_result, [])

    def test_sympy_json_failure_not_empty(self):
        """SymPy 工具即使失败也返回结构化 JSON，不应被判为空"""
        sympy_result = '{"success": false, "result": null, "error": "division by zero", "code": "..."}'
        assert not _is_empty_or_duplicate(sympy_result, [])

    def test_sympy_json_still_checks_duplicate(self):
        """SymPy JSON 结果不参与空结果检测，但仍可检查真正空白/标记"""
        assert _is_empty_or_duplicate("", [])
        assert _is_empty_or_duplicate("[搜索结果为空]", [])
