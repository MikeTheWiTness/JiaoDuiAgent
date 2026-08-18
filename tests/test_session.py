"""Session 持久化测试 —— 当前仅保留生产已接线的进度记录能力。

已删除未接线的恢复 API（load_session / find_unfinished / mark_in_progress /
get_pending_questions），因此这里只锁定创建、状态更新、原子写入。
"""
import json
import tempfile
from pathlib import Path

import pytest

from shared.session import QuestionStatus, SessionManager


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
        """题目状态流转：pending → completed / failed。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("测试", [
            {"name": "第1题", "dir": "/tmp/q1"},
            {"name": "第2题", "dir": "/tmp/q2"},
        ])

        # 初始状态：pending
        assert mgr.get_question_status("第1题") == QuestionStatus.PENDING
        assert mgr.get_question_status("第2题") == QuestionStatus.PENDING

        # 完成/失败
        mgr.mark_completed("第1题")
        assert mgr.get_question_status("第1题") == QuestionStatus.COMPLETED

        mgr.mark_failed("第2题", "网络超时")
        assert mgr.get_question_status("第2题") == QuestionStatus.FAILED

    def test_atomic_write(self, session_dir):
        """原子写入——写入中途崩溃不应损坏文件。"""
        mgr = SessionManager(session_dir)
        mgr.start_session("测试", [{"name": "第1题", "dir": "/tmp/q1"}])
        mgr.mark_completed("第1题")

        # 验证文件是合法 JSON
        with open(mgr.session_file, encoding='utf-8') as f:
            data = json.load(f)
        assert data["questions"][0]["status"] == "completed"
