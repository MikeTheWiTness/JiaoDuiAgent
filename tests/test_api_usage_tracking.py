"""Issue 011：API 用量追踪测试

验证 call_api 能正确提取和累计 token 使用量。
"""
from unittest.mock import MagicMock, patch

from core.api_client import StopReason, _accumulate_usage, _extract_usage, call_api
from core.session_context import SessionContext


def _make_ctx(api_url="http://test/v1", api_key="key", model="test-model", max_loops=20):
    """构造测试用的 SessionContext。"""
    return SessionContext(api_url=api_url, api_key=api_key, model=model, max_loops=max_loops)


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
            ctx=_make_ctx(),
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
            ctx=_make_ctx(max_loops=5),
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
            tools=[],  # 空工具列表，工具不会被实际执行
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
            ctx=_make_ctx(max_loops=0),  # 立即超限
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
            tools=[],
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
            ctx=_make_ctx(),
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
            ctx=_make_ctx(max_loops=5),
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
            tools=[],
        )

        # 第一次成功请求的 usage 应保留
        assert "usage" in result
        assert result["usage"]["total_tokens"] == 60
        assert result["stop_reason"] == StopReason.ERROR


class TestUsageCacheExtraction:
    """缓存命中字段的多厂商兼容提取（DeepSeek / 智谱GLM / OpenAI / vLLM）。"""

    def test_deepseek_style_top_level_fields(self):
        """DeepSeek 风格：顶层 prompt_cache_hit_tokens / prompt_cache_miss_tokens。"""
        u = _extract_usage({
            "usage": {
                "prompt_tokens": 1500, "completion_tokens": 300, "total_tokens": 1800,
                "prompt_cache_hit_tokens": 1200, "prompt_cache_miss_tokens": 300,
            }
        })
        assert u["prompt_cache_hit_tokens"] == 1200
        assert u["prompt_cache_miss_tokens"] == 300

    def test_glm_openai_style_nested_cached_tokens(self):
        """智谱 GLM / OpenAI 风格：嵌套 prompt_tokens_details.cached_tokens，未命中推导。"""
        u = _extract_usage({
            "usage": {
                "prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500,
                "prompt_tokens_details": {"cached_tokens": 800},
            }
        })
        assert u["prompt_cache_hit_tokens"] == 800
        # 未命中数缺失时由 prompt_tokens - hit 推导
        assert u["prompt_cache_miss_tokens"] == 400

    def test_responses_style_input_tokens_details(self):
        """Responses API 风格：嵌套 input_tokens_details.cached_tokens。"""
        u = _extract_usage({
            "usage": {
                "input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200,
                "input_tokens_details": {"cached_tokens": 600},
            }
        })
        assert u["prompt_tokens"] == 1000
        assert u["prompt_cache_hit_tokens"] == 600
        assert u["prompt_cache_miss_tokens"] == 400

    def test_no_cache_fields_no_cache_keys(self):
        """响应不带缓存字段时不产生缓存键，避免误报。"""
        u = _extract_usage({
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        })
        assert "prompt_cache_hit_tokens" not in u
        assert "prompt_cache_miss_tokens" not in u

    def test_missing_usage_returns_empty(self):
        """无 usage 字段时返回三键 0 且无缓存键；usage 非 dict 时返回空 dict。"""
        u = _extract_usage({"choices": []})
        assert u["total_tokens"] == 0
        assert "prompt_cache_hit_tokens" not in u
        assert _extract_usage({"usage": None}) == {}

    def test_accumulate_usage_with_cache_fields(self):
        """两种风格的缓存字段应能正确累加。"""
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        _accumulate_usage(total, _extract_usage({
            "usage": {
                "prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                "prompt_cache_hit_tokens": 90, "prompt_cache_miss_tokens": 10,
            }
        }))
        _accumulate_usage(total, _extract_usage({
            "usage": {
                "prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220,
                "prompt_tokens_details": {"cached_tokens": 150},
            }
        }))
        assert total["prompt_tokens"] == 300
        assert total["prompt_cache_hit_tokens"] == 240  # 90 + 150
        assert total["prompt_cache_miss_tokens"] == 60  # 10 + (200 - 150)

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_call_api_accumulates_cache_hit(self, mock_save, mock_dump, mock_post):
        """多轮调用时缓存命中字段应随 usage 一起累计。"""
        mock_dump.return_value = ""

        # 第1轮：冷启动，无命中
        resp1 = _make_mock_response(
            content="",
            usage={
                "prompt_tokens": 1500, "completion_tokens": 20, "total_tokens": 1520,
                "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 1500,
            },
            finish_reason="tool_calls",
        )
        resp1.json.return_value["choices"][0]["message"]["tool_calls"] = [
            {"id": "1", "function": {"name": "locate_paragraph", "arguments": '{"keywords":"test"}'}}
        ]
        # 第2轮：相同前缀命中，嵌套字段（智谱/OpenAI 风格）
        resp2 = _make_mock_response(
            content="校对完成",
            usage={
                "prompt_tokens": 1800, "completion_tokens": 80, "total_tokens": 1880,
                "prompt_tokens_details": {"cached_tokens": 1500},
            },
            finish_reason="stop",
        )
        mock_post.side_effect = [resp1, resp2]

        result = call_api(
            ctx=_make_ctx(max_loops=5),
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
            tools=[],
        )

        usage = result["usage"]
        assert usage["total_tokens"] == 3400  # 1520 + 1880
        assert usage["prompt_cache_hit_tokens"] == 1500  # 0 + 1500
        assert usage["prompt_cache_miss_tokens"] == 1800  # 1500 + (1800-1500)


class TestFormatUsageSummary:
    """Token 用量统计表的格式化（含缓存命中行）。"""

    def test_summary_with_cache_hit_shows_hit_rows(self):
        from core.defaults import _format_usage_summary

        text = _format_usage_summary({
            "prompt_tokens": 1800, "completion_tokens": 300, "total_tokens": 2100,
            "prompt_cache_hit_tokens": 1500, "prompt_cache_miss_tokens": 300,
        })
        assert "| 提示词 (prompt) | 1,800 |" in text
        assert "| 输入·缓存命中 | 1,500（83.3%） |" in text
        assert "| 输入·缓存未命中 | 300 |" in text
        assert "| **总计** | **2,100** |" in text

    def test_summary_without_cache_fields_omits_hit_rows(self):
        from core.defaults import _format_usage_summary

        text = _format_usage_summary({
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
        })
        assert "输入·缓存命中" not in text
        assert "输入·缓存未命中" not in text

    def test_summary_empty_usage_returns_empty(self):
        from core.defaults import _format_usage_summary

        assert _format_usage_summary({}) == ""
        assert _format_usage_summary(None) == ""
