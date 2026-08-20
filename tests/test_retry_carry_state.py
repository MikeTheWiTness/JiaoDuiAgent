"""Issue 052：重试携带状态续跑 —— 网络波动不再从零重建对话（ADR-0029 重试语义）。

覆盖验收：
- 工具循环中途可重试网络异常（mock）：退避后从已有对话继续，已完成工具不重复执行
- 续跑后的 token 用量为「中断前累计 + 续跑新增」，不重复计算中断前的轮次
- 首次请求失败的重试仍从零开始（现状行为）
- 不可重试错误（400）立即停止，不清空已积累的对话记录（快照保留首轮历史）
"""
import json

import requests

from core.api_client import (
    CHECKPOINT_FILENAME,
    StopReason,
    call_api,
)
from core.session_context import SessionContext


def _ctx(tmp_path, **kw):
    defaults = dict(api_url="http://x", api_key="k", model="m",
                    max_loops=5, output_dir=str(tmp_path))
    defaults.update(kw)
    return SessionContext(**defaults)


def _tool_choice(name):
    return {
        "message": {
            "role": "assistant",
            "content": f"需要调用 {name}",
            "tool_calls": [
                {"id": f"c_{name}", "type": "function",
                 "function": {"name": name, "arguments": "{}"}}
            ],
        },
        "finish_reason": "tool_calls",
    }


def _end_choice(content="最终结果"):
    return {"message": {"role": "assistant", "content": content},
            "finish_reason": "stop"}


def _sequenced(seq):
    """消费序列：进入序列即 raise（可重试/不可重试异常），否则原样返回。"""
    seq = list(seq)

    def _post(*a, **k):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return _post


class TestMidLoopRetry:

    def test_mid_loop_retry_carries_state(self, tmp_path):
        """工具循环中途网络异常：退避后携带已有对话继续，已完成工具不重复执行。"""
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path)
        executed = []

        def _execute(_tools, name, _args):
            executed.append(name)
            return f"{name} 结果"

        seq = [
            (_tool_choice("round1"), {"total_tokens": 1}),        # 首次请求 → 轮1
            requests.exceptions.ConnectionError("网络波动"),        # 轮1 后状态缓存前失败
            (_tool_choice("round2"), {"total_tokens": 2}),        # 重试后继续 → 轮2
            requests.exceptions.ConnectionError("再次波动"),        # 轮2 后再次失败
            (_end_choice(), {"total_tokens": 3}),                 # 第二次重试完成
        ]
        sleeps = []
        with mock.patch.object(api_client, "execute_tool", side_effect=_execute), \
                mock.patch.object(api_client, "_post_chat", side_effect=_sequenced(seq)), \
                mock.patch.object(api_client.time, "sleep",
                                  side_effect=lambda s: sleeps.append(s)):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.END_TURN
        # 完成工具只执行一次：round1、round2
        assert executed == ["round1", "round2"], f"重复执行了已完成工具: {executed}"
        # tool_calls_log 无重复
        assert [e["tool"] for e in result["tool_calls_log"]] == ["round1", "round2"]
        # 有退避等待（两次失败）
        assert sleeps and len(sleeps) == 2, f"应为 2 次退避: {sleeps}"
        # token 用量为中断前累计 + 续跑新增（1 + 2 + 3），不重复计算
        assert result["usage"]["total_tokens"] == 6, result["usage"]

    def test_first_request_failure_retries_from_scratch(self, tmp_path):
        """首次请求失败的重试仍从零开始（无历史重建对话）。"""
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path)
        executed = []

        def _execute(_tools, name, _args):
            executed.append(name)
            return f"{name} 结果"

        seq = [
            requests.exceptions.ConnectionError("首次请求失败"),     # 无任何历史
            (_tool_choice("round1"), {"total_tokens": 1}),
            (_end_choice(), {"total_tokens": 2}),
        ]
        with mock.patch.object(api_client, "execute_tool", side_effect=_execute), \
                mock.patch.object(api_client, "_post_chat", side_effect=_sequenced(seq)), \
                mock.patch.object(api_client.time, "sleep"):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.END_TURN
        # 从零开始：round1 是全新一轮（不是恢复的续跑）
        assert executed == ["round1"]
        assert [e["tool"] for e in result["tool_calls_log"]] == ["round1"]
        assert result["usage"]["total_tokens"] == 3

    def test_non_retryable_error_stops_and_keeps_accumulated(self, tmp_path):
        """不可重试错误（400）立即停止，重试不启动；已积累对话保留在快照。"""
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path, enable_checkpoint=True)   # 快照保留首轮历史
        executed = []

        def _execute(_tools, name, _args):
            executed.append(name)
            return f"{name} 结果"

        resp = requests.Response()
        resp.status_code = 400
        resp._content = b'{"error": "bad request"}'
        http_err = requests.exceptions.HTTPError("400 Client Error", response=resp)

        seq = [
            (_tool_choice("round1"), {"total_tokens": 1}),
            http_err,                                        # 400 → 不可重试，立即停止
            (_end_choice(), {"total_tokens": 99}),           # 不应被消费
        ]
        sleeps = []
        with mock.patch.object(api_client, "execute_tool", side_effect=_execute), \
                mock.patch.object(api_client, "_post_chat", side_effect=_sequenced(seq)), \
                mock.patch.object(api_client.time, "sleep",
                                  side_effect=lambda s: sleeps.append(s)):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.ERROR
        assert sleeps == [], "不可重试错误不应退避/重试"
        # 已完成的首轮工具仍保留在快照（不清空已积累的对话记录）
        data = json.loads((tmp_path / CHECKPOINT_FILENAME).read_text(encoding="utf-8"))
        assert any(m.get("role") == "assistant" for m in data["messages"])
        assert data["tool_calls_log"][0]["tool"] == "round1"
