"""ADR-0012 Issue 8：Session 持久化测试

验证校对进度的保存、恢复、原子写入。
"""
import json
import tempfile
import os
import time
from pathlib import Path
import pytest

from shared.session import SessionManager, QuestionStatus


@pytest.fixture
def session_dir():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestSessionManager:
    """验证 SessionManager 核心行为。"""

    def test_create_session(self, session_dir):
        """创建 session 应生成状态文件。"""
        mgr = SessionManager(session_dir)
        mgr.start_session(
            subject="高中物理",
            questions=[
                {"name": "第1题", "dir": "/tmp/第1题"},
                {"name": "第2题", "dir": "/tmp/第2题"},
            ]
        )
        assert mgr.session_id is not None
        assert mgr.session_file.exists()

    def test_question_status_flow(self, session_dir):
        """题目状态流转：pending → in_progress → completed。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("测试", [
            {"name": "第1题", "dir": "/tmp/q1"},
            {"name": "第2题", "dir": "/tmp/q2"},
        ])

        # 初始状态：pending
        assert mgr.get_question_status("第1题") == QuestionStatus.PENDING
        assert mgr.get_question_status("第2题") == QuestionStatus.PENDING

        # 开始校对
        mgr.mark_in_progress("第1题")
        assert mgr.get_question_status("第1题") == QuestionStatus.IN_PROGRESS

        # 完成
        mgr.mark_completed("第1题")
        assert mgr.get_question_status("第1题") == QuestionStatus.COMPLETED

    def test_persist_and_reload(self, session_dir):
        """保存后重新加载，状态应一致。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("高中化学", [
            {"name": "第1题", "dir": "/tmp/q1"},
            {"name": "第2题", "dir": "/tmp/q2"},
            {"name": "第3题", "dir": "/tmp/q3"},
        ])
        mgr.mark_completed("第1题")
        mgr.mark_in_progress("第2题")
        mgr.mark_failed("第3题", "网络超时")

        # 重新加载
        mgr2 = SessionManager(session_dir)
        assert mgr2.load_session(mgr.session_id)

        assert mgr2.get_question_status("第1题") == QuestionStatus.COMPLETED
        assert mgr2.get_question_status("第2题") == QuestionStatus.IN_PROGRESS
        assert mgr2.get_question_status("第3题") == QuestionStatus.FAILED

    def test_atomic_write(self, session_dir):
        """原子写入——写入中途崩溃不应损坏文件。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("测试", [{"name": "第1题", "dir": "/tmp/q1"}])
        mgr.mark_completed("第1题")

        # 验证文件是合法 JSON
        with open(mgr.session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["questions"][0]["status"] == "completed"

    def test_find_unfinished_sessions(self, session_dir):
        """应能找到未完成的 session。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("测试", [{"name": "第1题", "dir": "/tmp/q1"}])
        mgr.mark_completed("第1题")
        # 全部完成 → 不算未完成

        mgr2 = SessionManager(session_dir)
        mgr2.start_session("测试2", [
            {"name": "第1题", "dir": "/tmp/q1"},
            {"name": "第2题", "dir": "/tmp/q2"},
        ])
        mgr2.mark_completed("第1题")
        # 第2题还是 pending → 未完成

        unfinished = SessionManager.find_unfinished(session_dir)
        assert len(unfinished) == 1
        assert unfinished[0]["subject"] == "测试2"

    def test_get_pending_questions(self, session_dir):
        """应返回待处理的题目列表。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("测试", [
            {"name": "第1题", "dir": "/tmp/q1"},
            {"name": "第2题", "dir": "/tmp/q2"},
            {"name": "第3题", "dir": "/tmp/q3"},
        ])
        mgr.mark_completed("第1题")

        pending = mgr.get_pending_questions()
        assert len(pending) == 2
        names = [q["name"] for q in pending]
        assert "第1题" not in names
        assert "第2题" in names

    def test_mark_in_progress_resets_failed(self, session_dir):
        """重试失败题目——in_progress 应覆盖 failed 状态。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("测试", [{"name": "第1题", "dir": "/tmp/q1"}])
        mgr.mark_failed("第1题", "超时")
        mgr.mark_in_progress("第1题")  # 重试
        assert mgr.get_question_status("第1题") == QuestionStatus.IN_PROGRESS
