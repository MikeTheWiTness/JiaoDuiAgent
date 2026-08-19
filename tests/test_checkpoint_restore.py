"""Issue 051：快照恢复 —— 四重校验 + 损坏分流 + 图片重编码 + log 提示（ADR-0029 恢复侧）。

覆盖验收：
- 中断后重跑同一单元：自动续跑、不重放已完成工具、log 出现续跑提示行
- 批注评审模式/改题/换模型重跑：不恢复、删快照、从零开始
- 快照 JSON 损坏/版本不认识/缺字段：重命名 .corrupt 保留现场，本轮正常完成
- 恢复后图片按文件名重编码回填；缺失图片 log 警告且流程不中断
- 恢复后 total_usage 不清零，直接继续累加
- 删除快照后重跑：等价全新校对
"""
import json

from core.api_client import (
    CHECKPOINT_CORRUPT_FILENAME,
    CHECKPOINT_FILENAME,
    StopReason,
    call_api,
)
from core.session_context import SessionContext


def _ctx(tmp_path, **kw):
    defaults = dict(
        api_url="http://x", api_key="k", model="m",
        max_loops=2, output_dir=str(tmp_path), enable_checkpoint=True,
    )
    defaults.update(kw)
    return SessionContext(**defaults)


def _tool_choice(call_ids=("c1",), name="fake_tool"):
    return {
        "message": {
            "role": "assistant",
            "content": "需要查询",
            "tool_calls": [
                {"id": cid, "type": "function",
                 "function": {"name": name, "arguments": "{}"}}
                for cid in call_ids
            ],
        },
        "finish_reason": "tool_calls",
    }


def _end_choice(content="最终结果"):
    return {"message": {"role": "assistant", "content": content},
            "finish_reason": "stop"}


def _make_snapshot(tmp_path, *, title="第1题", prompt="提示", md_hash="hash-md",
                   model="m", images=(), image_paths=()):
    """制造一个 mid-loop 中断快照：首轮调用 fake_tool 后网络波动（ERROR），快照保留。

    返回用于重跑的 ctx（与快照同 q_dir / 同参数）。
    """
    from unittest import mock

    import requests

    from core import api_client

    ctx = _ctx(tmp_path, model=model)
    calls = {"n": 0}

    def _fake_post(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_choice(), {"total_tokens": 1}
        raise requests.exceptions.ConnectionError("波动")

    with mock.patch.object(api_client, "execute_tool", return_value="第一轮结果"), \
            mock.patch.object(api_client, "_post_chat", side_effect=_fake_post), \
            mock.patch.object(api_client.time, "sleep"):
        result = call_api(ctx, "文本", list(images), title, prompt, tools=[],
                          checkpoint_md_hash=md_hash, image_paths=list(image_paths))
    assert result["stop_reason"] == StopReason.ERROR
    assert (tmp_path / CHECKPOINT_FILENAME).exists()
    return ctx


class TestRestoreSuccess:

    def test_resume_without_replaying_tools(self, tmp_path):
        """中断后重跑同一单元：自动续跑、不重放已完成工具、log 有续跑提示行。"""
        from unittest import mock

        from core import api_client

        ctx = _make_snapshot(tmp_path)

        executed = []

        def _execute(_tools, tool_name, _args):
            executed.append(tool_name)
            return f"{tool_name} 结果"

        second_choice = _tool_choice(call_ids=("c2",), name="second_tool")
        with mock.patch.object(api_client, "execute_tool", side_effect=_execute), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(second_choice, {"total_tokens": 1}),
                                               (_end_choice(), {"total_tokens": 1})]), \
                mock.patch.object(api_client, "log") as mock_log:
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[],
                              checkpoint_md_hash="hash-md", image_paths=[])

        assert result["stop_reason"] == StopReason.END_TURN
        # 只执行恢复后的新工具，未重放已完成的首轮工具
        assert executed == ["second_tool"], f"重放了已完成工具: {executed}"
        # tool_calls_log 含中断前首轮 + 恢复后第二轮
        assert [e["tool"] for e in result["tool_calls_log"]] == ["fake_tool", "second_tool"]
        # 正常完成后快照被清除
        assert not (tmp_path / CHECKPOINT_FILENAME).exists()
        # 续跑提示行已 log
        log_msgs = [str(c) for c in mock_log.call_args_list]
        assert any("检测到中断快照" in m and "从断点续跑" in m for m in log_msgs), log_msgs

    def test_restore_usage_cumulative(self, tmp_path):
        """恢复后 token 用量含中断前的累计（total_usage 不清零）。"""
        from unittest import mock

        from core import api_client

        ctx = _make_snapshot(tmp_path)   # 首轮已消耗 total_tokens=1，写入快照
        second_choice = _tool_choice(call_ids=("c2",), name="second_tool")
        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(second_choice, {"total_tokens": 10}),
                                               (_end_choice(), {"total_tokens": 5})]):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[],
                              checkpoint_md_hash="hash-md", image_paths=[])

        assert result["stop_reason"] == StopReason.END_TURN
        # 中断前 1 + 中断后两轮 10 + 5 = 16，不含重放
        assert result["usage"]["total_tokens"] == 16, result["usage"]


class TestValidationMismatch:

    def test_prompt_mismatch_deletes_snapshot_and_restarts(self, tmp_path):
        """批注评审模式重跑（prompt 不同）：不恢复、删快照、从零开始。"""
        from unittest import mock

        from core import api_client

        ctx = _make_snapshot(tmp_path)

        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}),
                                               (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "文本", [], "第1题", "批注评审专用提示", tools=[],
                              checkpoint_md_hash="hash-md", image_paths=[])

        assert result["stop_reason"] == StopReason.END_TURN
        assert not (tmp_path / CHECKPOINT_FILENAME).exists(), "校验不匹配应删除快照"
        assert "批注评审专用提示" in str(result["messages"][0]["content"])

    def test_md_mismatch_deletes_snapshot_and_restarts(self, tmp_path):
        """编辑单元 md 后重跑：不恢复、删快照、从零开始。"""
        from unittest import mock

        from core import api_client

        ctx = _make_snapshot(tmp_path)

        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}),
                                               (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "新 md 文本", [], "第1题", "提示", tools=[],
                              checkpoint_md_hash="hash-md-CHANGED", image_paths=[])

        assert result["stop_reason"] == StopReason.END_TURN
        assert not (tmp_path / CHECKPOINT_FILENAME).exists()

    def test_model_mismatch_deletes_snapshot_and_restarts(self, tmp_path):
        """换模型后重跑：不恢复、删快照、从零开始。"""
        from unittest import mock

        from core import api_client

        _make_snapshot(tmp_path)                     # 快照 model="m"
        ctx = _ctx(tmp_path, model="other-model")    # 重跑换模型

        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}),
                                               (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[],
                              checkpoint_md_hash="hash-md", image_paths=[])

        assert result["stop_reason"] == StopReason.END_TURN
        assert not (tmp_path / CHECKPOINT_FILENAME).exists()


class TestCorruption:

    def _run_fresh_ok(self, tmp_path, *, prompt="提示", md_hash="hash-md"):
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path)
        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}),
                                               (_end_choice(), {"total_tokens": 1})]):
            return call_api(ctx, "文本", [], "第1题", prompt, tools=[],
                            checkpoint_md_hash=md_hash, image_paths=[]), ctx

    def test_corrupt_json_renamed_and_run_completes(self, tmp_path):
        """快照 JSON 损坏：重命名 .corrupt 保留现场，从零开始，本轮正常完成。"""
        snap = tmp_path / CHECKPOINT_FILENAME
        snap.write_text("这是非法 JSON {{{", encoding="utf-8")
        result, _ = self._run_fresh_ok(tmp_path)
        assert result["stop_reason"] == StopReason.END_TURN
        assert not snap.exists()
        assert (tmp_path / CHECKPOINT_CORRUPT_FILENAME).exists()

    def test_unknown_schema_version_renamed_corrupt(self, tmp_path):
        snap = tmp_path / CHECKPOINT_FILENAME
        snap.write_text(json.dumps({"schema_version": 999, "messages": []}), encoding="utf-8")
        result, _ = self._run_fresh_ok(tmp_path)
        assert result["stop_reason"] == StopReason.END_TURN
        assert not snap.exists()
        assert (tmp_path / CHECKPOINT_CORRUPT_FILENAME).exists()

    def test_missing_required_field_renamed_corrupt(self, tmp_path):
        snap = tmp_path / CHECKPOINT_FILENAME
        # 缺 messages/total_usage/tool_calls_log 等必需字段
        snap.write_text(json.dumps({"schema_version": 1, "q_title": "第1题"}), encoding="utf-8")
        result, _ = self._run_fresh_ok(tmp_path)
        assert result["stop_reason"] == StopReason.END_TURN
        assert not snap.exists()
        assert (tmp_path / CHECKPOINT_CORRUPT_FILENAME).exists()


class TestImageRestore:

    def test_reencode_images_and_drop_missing(self, tmp_path):
        """恢复时图片按名重编码回填；缺失图片 log 警告且流程不中断。"""
        from unittest import mock

        from core import api_client

        img_dir = tmp_path / "images"
        img_dir.mkdir()
        (img_dir / "a.png").write_bytes(b"ABC")      # base64 → 4UJD

        image = {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64,QUJD"}}
        ctx = _make_snapshot(tmp_path, images=[image, image],
                             image_paths=["a.png", "missing.png"])

        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_end_choice(), {"total_tokens": 1})]), \
                mock.patch.object(api_client, "log") as mock_log:
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[],
                              checkpoint_md_hash="hash-md", image_paths=["a.png", "missing.png"])

        assert result["stop_reason"] == StopReason.END_TURN
        # 恢复后的 user 消息：图片按名重编码；缺失图降级为空 URL
        user_msgs = [m for m in result["messages"] if m.get("role") == "user"]
        parts = user_msgs[0]["content"]
        image_parts = [p for p in parts if p.get("type") == "image_url"]
        assert image_parts[0]["image_url"]["url"] == "data:image/png;base64,QUJD"
        assert image_parts[1]["image_url"]["url"] == ""
        # 缺失图片有 log 警告（流程不中断）
        log_msgs = [str(c) for c in mock_log.call_args_list]
        assert any("图片缺失" in m for m in log_msgs), log_msgs


class TestNoSnapshotIsFresh:

    def test_deleted_snapshot_is_fresh(self, tmp_path):
        """用户删除快照文件后重跑：等价全新校对（首轮工具重新执行）。"""
        from unittest import mock

        from core import api_client

        ctx = _make_snapshot(tmp_path)
        # 用户删除快照
        (tmp_path / CHECKPOINT_FILENAME).unlink()

        executed = []

        def _execute(_tools, tool_name, _args):
            executed.append(tool_name)
            return "有结果"

        with mock.patch.object(api_client, "execute_tool", side_effect=_execute), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}),
                                               (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[],
                              checkpoint_md_hash="hash-md", image_paths=[])

        assert result["stop_reason"] == StopReason.END_TURN
        # 全新校对：首轮 fake_tool 重新执行（而非从断点续跑）
        assert executed == ["fake_tool"]
