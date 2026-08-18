"""校对 Session 持久化 —— 记录当前校对进度。

使用方式：
    from shared.session import SessionManager

    mgr = SessionManager(session_dir)
    mgr.start_session("高中物理", questions)
    mgr.mark_completed("第1题")
    mgr.mark_failed("第1题", "错误信息")
"""
import json
import os
import threading
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

# 跨实例串行化写入（多 session 并发写不交错损坏）
_SAVE_LOCK = threading.Lock()


class QuestionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionManager:
    """校对进度管理器。"""

    def __init__(self, session_dir: Path):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_id: str | None = None
        self.session_file: Path | None = None
        self._data: dict | None = None

    # ---- 创建 ----

    def start_session(self, subject: str, questions: list[dict]) -> str:
        """创建新 session。

        Args:
            subject: 学科名称
            questions: [{"name": "第1题", "dir": "/path/to/q1"}, ...]

        Returns:
            session_id
        """
        self.session_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()

        self._data = {
            "session_id": self.session_id,
            "subject": subject,
            "start_time": now,
            "last_update": now,
            "questions": [
                {
                    "name": q["name"],
                    "dir": q.get("dir", ""),
                    "status": QuestionStatus.PENDING.value,
                    "error": None,
                }
                for q in questions
            ],
        }

        self.session_file = self.session_dir / f"session_{self.session_id}.json"
        self._save()
        return self.session_id

    # ---- 状态更新 ----

    def mark_completed(self, name: str):
        self._update_status(name, QuestionStatus.COMPLETED)

    def mark_failed(self, name: str, error: str = ""):
        self._update_status(name, QuestionStatus.FAILED, error=error)

    def _update_status(self, name: str, status: QuestionStatus, error: str = None):
        if not self._data:
            return
        for q in self._data["questions"]:
            if q["name"] == name:
                q["status"] = status.value
                if error is not None:
                    q["error"] = error
                break
        self._data["last_update"] = datetime.now(UTC).isoformat()
        self._save()

    # ---- 查询 ----

    def get_question_status(self, name: str) -> QuestionStatus | None:
        if not self._data:
            return None
        for q in self._data["questions"]:
            if q["name"] == name:
                return QuestionStatus(q["status"])
        return None

    # ---- 持久化 ----

    def _save(self):
        """原子写入——先写唯一临时文件再 rename，加锁串行化。"""
        if not self.session_file or not self._data:
            return
        tmp_path = self.session_file.with_name(
            f"{self.session_file.name}.{uuid.uuid4().hex[:8]}.tmp")
        with _SAVE_LOCK:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.session_file)  # 原子操作
