"""Issue 011：API 用量追踪测试

验证 call_api 能正确提取和累计 token 使用量。
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from core.api_client import call_api, StopReason


def _make_mock_response(content: str, usage: dict = None, finish_reason: str = "stop"):
    """构造模拟的 API 响应对象。"""
    if usage is None:
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{
            "message": {"content": content, "role": "assistant"},
            "finish_reason": finish_reason,
        }],
        "usage": usage,
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


class TestApiUsageTracking:
    """验证 call_api 的 usage 提取和累计功能。"""

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_single_call_returns_usage(self, mock_save, mock_dump, mock_post):
        """单次 API 调用返回的 result 应包含 usage 字段。"""
        mock_dump.return_value = ""
        mock_post.return_value = _make_mock_response("校对完成")

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
        )

        assert "usage" in result, f"result 应包含 'usage' 字段，实际 keys: {list(result.keys())}"
        assert result["usage"] is not None
        assert result["usage"]["prompt_tokens"] == 100
        assert result["usage"]["completion_tokens"] == 50
        assert result["usage"]["total_tokens"] == 150

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_multi_turn_accumulates_usage(self, mock_save, mock_dump, mock_post):
        """多轮工具调用应累计所有 API 请求的 usage。"""
        mock_dump.return_value = ""

        # 第1轮：返回工具调用
        resp1 = _make_mock_response(
            content="",
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            finish_reason="tool_calls",
        )
        resp1.json.return_value["choices"][0]["message"]["tool_calls"] = [
            {"id": "1", "function": {"name": "locate_paragraph", "arguments": '{"keywords":"test"}'}}
        ]

        # 第2轮：最终回复
        resp2 = _make_mock_response(
            content="校对完成",
            usage={"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
            finish_reason="stop",
        )

        mock_post.side_effect = [resp1, resp2]

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
            tools=[],  # 空工具列表，工具不会被实际执行
            max_loops=5,
        )

        assert "usage" in result
        usage = result["usage"]
        # 两轮请求的 token 应累计
        assert usage["prompt_tokens"] == 300  # 100 + 200
        assert usage["completion_tokens"] == 100  # 20 + 80
        assert usage["total_tokens"] == 400  # 120 + 280

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_usage_included_in_stop_reason_max_turns(self, mock_save, mock_dump, mock_post):
        """max_turns 停止时也应包含 usage。"""
        mock_dump.return_value = ""

        resp = _make_mock_response(
            content="",
            usage={"prompt_tokens": 500, "completion_tokens": 0, "total_tokens": 500},
            finish_reason="tool_calls",
        )
        resp.json.return_value["choices"][0]["message"]["tool_calls"] = [
            {"id": "1", "function": {"name": "locate_paragraph", "arguments": '{"keywords":"x"}'}}
        ]

        mock_post.return_value = resp

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
            tools=[],
            max_loops=0,  # 立即超限
        )

        assert "usage" in result
        assert result["stop_reason"] == StopReason.MAX_TURNS
        assert result["usage"]["total_tokens"] > 0

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_missing_usage_handled_gracefully(self, mock_save, mock_dump, mock_post):
        """API 响应缺少 usage 字段时不应报错，返回 None 或空结构。"""
        mock_dump.return_value = ""

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {"content": "done", "role": "assistant"},
                "finish_reason": "stop",
            }],
            # 无 usage 字段
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
        )

        # 不应崩溃
        assert "content" in result
        # usage 可能是 None 或空 dict
        usage = result.get("usage")
        assert usage is None or usage == {} or usage.get("total_tokens", 0) == 0

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_usage_preserved_on_error(self, mock_save, mock_dump, mock_post):
        """API 调用异常时，usage 应保留之前已成功获取的部分。"""
        mock_dump.return_value = ""

        # 第一次成功
        resp1 = _make_mock_response(
            content="",
            usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
            finish_reason="tool_calls",
        )
        resp1.json.return_value["choices"][0]["message"]["tool_calls"] = [
            {"id": "1", "function": {"name": "read_section", "arguments": '{"start":1,"end":1}'}}
        ]

        # 第二次抛出异常
        import requests as req_mod
        mock_post.side_effect = [resp1, req_mod.exceptions.Timeout("timeout")]

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
            tools=[],
            max_loops=5,
        )

        # 第一次成功请求的 usage 应保留
        assert "usage" in result
        assert result["usage"]["total_tokens"] == 60
        assert result["stop_reason"] == StopReason.ERROR
