"""测试 call_api 核心改造：StopReason、压缩历史、返回值扩展"""
from core.api_client import (
    StopReason,
    _compress_history,
    _is_empty_or_duplicate,
    _save_conversation_log,
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


class TestRunToolLoopRobustness:
    """回归：_run_tool_loop 对异常 API 响应的健壮性。"""

    def _make_ctx(self, tmp_path):
        from core.session_context import SessionContext
        return SessionContext(api_url="http://x", api_key="k", model="m",
                              max_loops=1, output_dir=str(tmp_path))

    def _run_loop(self, ctx, first_choice):
        from unittest import mock

        from core import api_client

        messages = [{"role": "system", "content": "系统提示"}]
        end_turn_choice = {"message": {"role": "assistant", "content": "最终结果"},
                           "finish_reason": "stop"}
        # 循环内第一次 _post_chat 即返回 end_turn（消耗顺序：仅此一个响应）
        responses = iter([end_turn_choice])

        with mock.patch.object(api_client, "_post_chat",
                               side_effect=lambda *a, **k: (next(responses), {"total_tokens": 1})):
            return api_client._run_tool_loop(
                ctx,
                first_choice,
                messages,
                tool_instances=[],
                openai_tools=[],
                tool_calls_log=[],
                initial_header="",
                payload={},
                chat_url="http://x",
                headers={},
                reasoning_effort=None,
                total_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

    def test_missing_tool_calls_key_no_crash(self, tmp_path):
        """回归：finish_reason=tool_calls 但 message 无 tool_calls 键 → 不抛 KeyError"""
        from core.api_client import StopReason
        ctx = self._make_ctx(tmp_path)
        choice = {"message": {"content": None}, "finish_reason": "tool_calls"}
        result = self._run_loop(ctx, choice)
        # 无工具可执行 → 不崩溃，走配额/触顶路径正常收尾
        assert result.stop_reason in (StopReason.MAX_TURNS, StopReason.END_TURN)
        assert result.content is not None

    def test_reasoning_content_stripped_from_loop_messages(self, tmp_path):
        """回归：回传 messages 的 assistant 消息必须剔除 reasoning_content"""
        choice = {
            "message": {
                "role": "assistant",
                "content": None,
                "reasoning_content": "内部思考过程不应回传",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "未知工具", "arguments": "{}"}}
                ],
            },
            "finish_reason": "tool_calls",
        }
        ctx = self._make_ctx(tmp_path)
        result = self._run_loop(ctx, choice)
        # 工具已执行（未知工具返回错误串），消息被回传
        assert any("tool" in m["role"] for m in result.messages)
        for m in result.messages:
            assert "reasoning_content" not in m, f"messages 中残留 reasoning_content: {m}"
        # tool_calls 必须保留（OpenAI 协议要求 assistant 消息回显 tool_calls）
        assistant_msgs = [m for m in result.messages
                          if m.get("role") == "assistant" and m.get("tool_calls")]
        assert assistant_msgs, "assistant 消息丢失 tool_calls 字段（过度剔除）"
        assert assistant_msgs[0]["tool_calls"][0]["id"] == "call_1"
        # 思考内容不能随消息丢弃：必须按轮次收集，供 _save_conversation_log 落盘
        assert result.reasonings.get(1) == "内部思考过程不应回传"

    def test_conversation_log_contains_reasoning(self, tmp_path):
        """回归：reasoning_content 必须逐轮写入 _API对话记录.md

        修复前：reasoning_content 在回传消息前被剔除，对话记录只遍历 messages，
        思考内容既不在对话记录、也不在消息中——唯一去处是 _校对报告.md。
        """
        from unittest import mock

        from core import api_client
        ctx = self._make_ctx(tmp_path)
        tool_choice = {
            "message": {
                "role": "assistant",
                "content": "我需要搜索确认",
                "reasoning_content": "第一轮推理：先查资料",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "未知工具", "arguments": "{}"}}
                ],
            },
            "finish_reason": "tool_calls",
        }
        end_choice = {
            "message": {"role": "assistant", "content": "无问题",
                        "reasoning_content": "第二轮推理：确认无错误"},
            "finish_reason": "stop",
        }
        responses = iter([tool_choice, end_choice])
        with mock.patch.object(
                api_client, "_post_chat",
                side_effect=lambda *a, **k: (next(responses), {"total_tokens": 1})):
            result = api_client.call_api(
                ctx, "题目内容", [], "第1题", "系统提示", tools=[])
        assert result["stop_reason"] == "end_turn"
        log_path = tmp_path / "_API对话记录.md"
        assert log_path.exists()
        text = log_path.read_text(encoding="utf-8")
        assert "### 第1轮 — LLM 请求工具调用" in text
        assert "第一轮推理：先查资料" in text
        assert "### 第2轮 — LLM 最终回复" in text
        assert "第二轮推理：确认无错误" in text
        assert "推理内容（reasoning_content）" in text

    def test_interrupted_saves_conversation_log(self, tmp_path):
        """M7：工具循环中断路径必须补存主 _API对话记录.md"""
        import dataclasses
        import threading

        from core import api_client
        from core.api_client import StopReason

        ctx = dataclasses.replace(
            self._make_ctx(tmp_path),
            interrupt_event=threading.Event(),
        )
        ctx.interrupt_event.set()
        choice = {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "fake_tool", "arguments": "{}"}}
                ],
            },
            "finish_reason": "tool_calls",
        }
        result = api_client._run_tool_loop(
            ctx, choice,
            messages=[{"role": "user", "content": "题目"}],
            tool_instances=[], openai_tools=[],
            tool_calls_log=[], initial_header="# HEADER",
            payload={}, chat_url="http://x", headers={},
            reasoning_effort=None,
            total_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        assert result.stop_reason == StopReason.INTERRUPTED
        log_path = tmp_path / "_API对话记录.md"
        assert log_path.exists()
        text = log_path.read_text(encoding="utf-8")
        assert "# HEADER" in text
        assert "题目" in text

    def test_tool_loop_saves_main_conversation_log(self, tmp_path):
        """M7：TOOL_LOOP 压缩路径必须补存主 _API对话记录.md"""
        from unittest import mock

        from core import api_client
        from core.api_client import StopReason

        ctx = self._make_ctx(tmp_path)
        tool_choice = {
            "message": {
                "role": "assistant",
                "content": "连续空结果",
                "tool_calls": [
                    {"id": f"call_{i}", "function": {"name": "fake_tool", "arguments": "{}"}}
                    for i in range(3)
                ],
            },
            "finish_reason": "tool_calls",
        }
        end_choice = {
            "message": {"role": "assistant", "content": "压缩后的最终回复"},
            "finish_reason": "stop",
        }

        with mock.patch.object(api_client, "execute_tool", return_value=""), \
                mock.patch.object(api_client, "_post_chat",
                                  return_value=(end_choice, {"total_tokens": 1})):
            result = api_client._run_tool_loop(
                ctx, tool_choice,
                messages=[{"role": "user", "content": "题目"}],
                tool_instances=[], openai_tools=[],
                tool_calls_log=[], initial_header="# HEADER",
                payload={}, chat_url="http://x", headers={},
                reasoning_effort=None,
                total_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

        assert result.stop_reason == StopReason.TOOL_LOOP
        main_log = tmp_path / "_API对话记录.md"
        full_log = tmp_path / "_API对话记录_full.md"
        assert main_log.exists(), "TOOL_LOOP 应保存主日志"
        assert full_log.exists(), "TOOL_LOOP 压缩前应保存 _full 日志"
        assert "压缩后的最终回复" in main_log.read_text(encoding="utf-8")

    def test_conversation_log_does_not_truncate_long_content(self, tmp_path):
        """M7：对话记录不再截断 LLM 原始返回/工具返回/参数"""
        long_text = "长内容" * 5000  # 远超旧 5000/10000 截断阈值
        messages = [
            {"role": "user", "content": long_text},
            {"role": "assistant", "content": long_text},
            {"role": "tool", "content": long_text},
        ]
        _save_conversation_log(
            messages, str(tmp_path), q_title="t", initial_header="# HEADER",
        )
        text = (tmp_path / "_API对话记录.md").read_text(encoding="utf-8")
        assert long_text in text
        assert "[截断]" not in text

    def test_429_retry_after_respected(self, tmp_path):
        """回归：429 响应的 Retry-After 必须影响退避时长"""
        from unittest import mock

        import requests

        from core import api_client
        from core.api_client import StopReason
        from core.session_context import SessionContext

        ctx = SessionContext(api_url="http://x", api_key="k", model="m",
                             max_loops=1, output_dir=str(tmp_path))
        sleeps = []

        def _fake_post(*a, **k):
            # 走真实 _classify_error 路径：HTTP 429 + Retry-After: 12
            resp = requests.Response()
            resp.status_code = 429
            resp.headers["Retry-After"] = "12"
            raise requests.exceptions.HTTPError("429 Too Many Requests", response=resp)

        with mock.patch.object(api_client.requests, "post", side_effect=_fake_post), \
                mock.patch.object(api_client.time, "sleep", side_effect=lambda s: sleeps.append(s)):
            result = api_client.call_api(
                ctx, "文本", [], "测试题", "提示词", tools=None)
        # 退避时长 >= 服务器建议的 12s（指数退避仅 5s）
        assert sleeps, "应有退避等待"
        assert sleeps[0] >= 12, f"退避 {sleeps[0]}s < Retry-After 12s"
        assert result["stop_reason"] == StopReason.ERROR
