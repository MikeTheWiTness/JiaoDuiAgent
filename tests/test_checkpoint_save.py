"""Issue 050：快照保存 —— 轮次边界 + 原子写 + 生命周期 + 门控（ADR-0029 保存侧）。

覆盖验收：
- enable_checkpoint 默认 False，非校对主流程路径不产生快照
- 工具循环中断/ERROR 后保留快照，messages 协议合法（无悬空 tool_call_id）
- 单元正常完成（END_TURN / MAX_TURNS / TOOL_LOOP）后删除快照
- 快照含校验四字段 + schema_version；图片以文件名清单、无 base64
- md_hash 取自 pre_hook 之前的原始单元文本
- 并行多单元快照互不干扰
"""
import json
import threading

from core.api_client import (
    CHECKPOINT_FILENAME,
    StopReason,
    _stable_hash,
    call_api,
)
from core.session_context import SessionContext


def _ctx(tmp_path, **kw):
    defaults = dict(
        api_url="http://x", api_key="k", model="m",
        max_loops=2, output_dir=str(tmp_path),
    )
    defaults.update(kw)
    return SessionContext(**defaults)


def _tool_choice(call_ids=("c1",)):
    return {
        "message": {
            "role": "assistant",
            "content": "需要查询",
            "tool_calls": [
                {"id": cid, "type": "function",
                 "function": {"name": "fake_tool", "arguments": "{}"}}
                for cid in call_ids
            ],
        },
        "finish_reason": "tool_calls",
    }


def _end_choice(content="最终结果"):
    return {"message": {"role": "assistant", "content": content},
            "finish_reason": "stop"}


class TestGating:

    def test_enable_checkpoint_default_false(self):
        ctx = SessionContext(api_url="http://x", api_key="k", model="m")
        assert ctx.enable_checkpoint is False

    def test_disabled_flow_produces_no_snapshot(self, tmp_path):
        """门控：enable_checkpoint=False（格式修正/智能分割/e2e 同路径）不产生快照。"""
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path)  # enable_checkpoint 默认 False
        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}), (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.END_TURN
        assert not (tmp_path / CHECKPOINT_FILENAME).exists()


class TestLifecycle:

    def test_error_retains_snapshot_with_clean_messages(self, tmp_path):
        """ERROR 后保留快照，且 messages 协议合法（无悬空 tool_call_id）。"""
        from unittest import mock

        import requests

        from core import api_client

        ctx = _ctx(tmp_path, enable_checkpoint=True)
        calls = {"n": 0}

        def _fake_post(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return _tool_choice(), {"total_tokens": 1}
            raise requests.exceptions.ConnectionError("网络波动")

        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat", side_effect=_fake_post), \
                mock.patch.object(api_client.time, "sleep"):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.ERROR
        snap_path = tmp_path / CHECKPOINT_FILENAME
        assert snap_path.exists(), "ERROR 后应保留快照"
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        # 协议合法：每个 tool_call_id 都有且仅有一条对应的 tool 消息
        tool_count = {}
        for msg in data["messages"]:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tool_count[tc["id"]] = []
            elif msg.get("role") == "tool":
                tool_count.setdefault(msg["tool_call_id"], []).append(msg)
        assert tool_count, "快照 messages 应含工具调用消息"
        for cid, tools in tool_count.items():
            assert len(tools) == 1, f"tool_call_id {cid} 有 {len(tools)} 条 tool 消息（应为 1）"

    def test_normal_completion_deletes_snapshot(self, tmp_path):
        """END_TURN 正常完成后删除快照。"""
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path, enable_checkpoint=True)
        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}), (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.END_TURN
        assert not (tmp_path / CHECKPOINT_FILENAME).exists()

    def test_max_turns_completion_deletes_snapshot(self, tmp_path):
        """MAX_TURNS 正常完成后删除快照。"""
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path, enable_checkpoint=True, max_loops=1)
        # loop 进入→运行 1 轮→触顶 MAX_TURNS→压缩后返回 end_turn
        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(_tool_choice(), {"total_tokens": 1}), (_tool_choice(), {"total_tokens": 1}), (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.MAX_TURNS
        assert not (tmp_path / CHECKPOINT_FILENAME).exists()

    def test_tool_loop_completion_deletes_snapshot(self, tmp_path):
        """TOOL_LOOP 正常完成后删除快照。"""
        from unittest import mock

        from core import api_client

        ctx = _ctx(tmp_path, enable_checkpoint=True)
        # 一轮内 3 次空结果 → TOOL_LOOP 压缩路径
        choice = _tool_choice(call_ids=("c1", "c2", "c3"))
        with mock.patch.object(api_client, "execute_tool", return_value=""), \
                mock.patch.object(api_client, "_post_chat",
                                  side_effect=[(choice, {"total_tokens": 1}), (_end_choice(), {"total_tokens": 1})]):
            result = call_api(ctx, "文本", [], "第1题", "提示", tools=[])

        assert result["stop_reason"] == StopReason.TOOL_LOOP
        assert not (tmp_path / CHECKPOINT_FILENAME).exists()


class TestSnapshotContent:

    def _run_error_with_checkpoint(self, tmp_path, images=(), image_paths=()):
        from unittest import mock

        import requests

        from core import api_client

        ctx = _ctx(tmp_path, enable_checkpoint=True)
        calls = {"n": 0}

        def _fake_post(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return _tool_choice(), {"total_tokens": 1}
            raise requests.exceptions.ConnectionError("网络波动")

        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat", side_effect=_fake_post), \
                mock.patch.object(api_client.time, "sleep"):
            return call_api(ctx, "文本", list(images), "第1题", "提示", tools=[],
                            checkpoint_md_hash="hash-md", image_paths=list(image_paths))

    def test_snapshot_contains_validation_fields(self, tmp_path):
        self._run_error_with_checkpoint(tmp_path)
        data = json.loads((tmp_path / CHECKPOINT_FILENAME).read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert data["q_title"] == "第1题"
        assert data["prompt_hash"] == _stable_hash("提示")
        assert data["md_hash"] == "hash-md"
        assert data["model"] == "m"
        assert data["image_paths"] == []

    def test_snapshot_images_as_paths_without_base64(self, tmp_path):
        image_a = {"type": "image_url",
                   "image_url": {"url": "data:image/png;base64,QUJD"}}
        image_b = {"type": "image_url",
                   "image_url": {"url": "data:image/jpeg;base64,REVG"}}
        self._run_error_with_checkpoint(tmp_path, images=[image_a, image_b],
                                        image_paths=["a.png", "b.png"])
        snap_path = tmp_path / CHECKPOINT_FILENAME
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        assert data["image_paths"] == ["a.png", "b.png"]
        blob = snap_path.read_text(encoding="utf-8")
        assert "base64" not in blob, "快照不应含 base64 数据"
        assert "data:image" not in blob, "快照不应含 data URL"
        # 消息中图片部分被替换为文件名引用
        user_msgs = [m for m in data["messages"] if m.get("role") == "user"]
        user_parts = user_msgs[0]["content"]
        image_parts = [p for p in user_parts if p.get("type") == "image_url"]
        assert image_parts[0]["image_url"]["url"] == "checkpoint:a.png"
        assert image_parts[1]["image_url"]["url"] == "checkpoint:b.png"


class TestParallelIsolation:

    def test_parallel_units_isolated(self, tmp_path):
        """并行多单元各目录快照互不干扰（原子写无交错损坏）。"""
        from unittest import mock

        import requests

        from core import api_client

        dir_a = tmp_path / "unitA"
        dir_b = tmp_path / "unitB"
        dir_a.mkdir()
        dir_b.mkdir()
        results = {}
        # 线程安全的 mock：per-thread 计数，同一 mock 供两线程共用，
        # 避免两线程并发 patch 同名全局导致 restore 错乱（泄漏到后续测试）
        local = threading.local()

        def _fake_post(*a, **k):
            n = getattr(local, "n", 0) + 1
            local.n = n
            if n == 1:
                return _tool_choice(), {"total_tokens": 1}
            raise requests.exceptions.ConnectionError("波动")

        def _run(d, title):
            ctx = _ctx(d, enable_checkpoint=True)
            results[title] = call_api(ctx, "文本", [], title, "提示", tools=[])

        threads = [threading.Thread(target=_run, args=(dir_a, "A题")),
                   threading.Thread(target=_run, args=(dir_b, "B题"))]
        # 单一 patch 上下文（主线程），两线程共享同一 `_post_chat` mock
        with mock.patch.object(api_client, "execute_tool", return_value="有结果"), \
                mock.patch.object(api_client, "_post_chat", side_effect=_fake_post), \
                mock.patch.object(api_client.time, "sleep"):
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert results["A题"]["stop_reason"] == StopReason.ERROR
        assert results["B题"]["stop_reason"] == StopReason.ERROR

        snap_a = json.loads((dir_a / CHECKPOINT_FILENAME).read_text(encoding="utf-8"))
        snap_b = json.loads((dir_b / CHECKPOINT_FILENAME).read_text(encoding="utf-8"))
        assert snap_a["q_title"] == "A题"
        assert snap_b["q_title"] == "B题"
        assert (dir_a / CHECKPOINT_FILENAME).exists()
        assert (dir_b / CHECKPOINT_FILENAME).exists()
        # 无残留临时文件
        assert not (dir_a / "_校对续传.tmp").exists()
        assert not (dir_b / "_校对续传.tmp").exists()


class TestDefaultProofreadOneMdHash:

    def test_md_hash_from_pre_hook_original_text(self, tmp_path):
        """md 哈希取自 pre_hook 之前的原始单元文本（前置参考注入不改变哈希值）。"""
        from unittest import mock

        from core import defaults
        from core.api_client import StopReason

        raw_md = "原始单元内容"
        patched_md = "原始单元内容\n\n## 前置参考\n动态注入内容"

        captured = {}

        def _fake_call_api(ctx, md_text, images, q_title, system_prompt, tools=None,
                           checkpoint_md_hash=None, image_paths=None):
            captured["md_hash"] = checkpoint_md_hash
            captured["md_text"] = md_text
            return {
                "content": "校对结果", "tool_calls_log": [], "reasoning": "",
                "usage": {}, "stop_reason": StopReason.END_TURN,
            }

        q_dir = tmp_path / "第1题"
        q_dir.mkdir()

        def _pre_hook(md):
            return patched_md

        with mock.patch.object(defaults, "read_md_for_unit", return_value=raw_md), \
                mock.patch.object(defaults, "call_api", side_effect=_fake_call_api), \
                mock.patch.object(defaults, "save_proofread_json"), \
                mock.patch.object(defaults, "_enforce_format", return_value=(True, [])), \
                mock.patch.object(defaults, "_format_tool_calls_summary", return_value=""):
            res = defaults.default_proofread_one(
                _ctx(tmp_path, enable_checkpoint=False), str(q_dir), "第1题",
                prompt="提示", tools=[], generate_pdf=False,
                pre_hook=_pre_hook, archive_root=str(tmp_path),
            )

        assert res["success"] is True
        # 传给 call_api 的是 hook 后文本
        assert captured["md_text"] == patched_md
        # 但 md_hash 是 pre_hook 之前的原始文本哈希
        assert captured["md_hash"] == _stable_hash(raw_md)
        assert captured["md_hash"] != _stable_hash(patched_md)
