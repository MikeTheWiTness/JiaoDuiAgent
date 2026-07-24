"""校对 Session 持久化 —— 记录进度，支持中断恢复。

使用方式：
    from shared.session import SessionManager

    mgr = SessionManager(session_dir)
    mgr.start_session("高中物理", questions)
    mgr.mark_in_progress("第1题")
    mgr.mark_completed("第1题")

    # 恢复
    unfinished = SessionManager.find_unfinished(session_dir)
"""
import json
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class QuestionStatus(str, Enum):
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
        now = datetime.now(timezone.utc).isoformat()

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

    def mark_in_progress(self, name: str):
        self._update_status(name, QuestionStatus.IN_PROGRESS)

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
        self._data["last_update"] = datetime.now(timezone.utc).isoformat()
        self._save()

    # ---- 查询 ----

    def get_question_status(self, name: str) -> QuestionStatus | None:
        if not self._data:
            return None
        for q in self._data["questions"]:
            if q["name"] == name:
                return QuestionStatus(q["status"])
        return None

    def get_pending_questions(self) -> list[dict]:
        """返回未完成的题目列表。"""
        if not self._data:
            return []
        return [
            q for q in self._data["questions"]
            if q["status"] in (QuestionStatus.PENDING.value, QuestionStatus.IN_PROGRESS.value)
        ]

    def is_all_done(self) -> bool:
        return len(self.get_pending_questions()) == 0

    # ---- 持久化 ----

    def _save(self):
        """原子写入——先写临时文件再 rename。"""
        if not self.session_file or not self._data:
            return
        tmp_path = self.session_file.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.session_file)  # 原子操作

    def load_session(self, session_id: str) -> bool:
        """从文件加载已有 session。"""
        self.session_id = session_id
        self.session_file = self.session_dir / f"session_{session_id}.json"
        if not self.session_file.exists():
            return False
        with open(self.session_file, encoding="utf-8") as f:
            self._data = json.load(f)
        return True

    # ---- 静态方法 ----

    @staticmethod
    def find_unfinished(session_dir: Path) -> list[dict]:
        """查找所有未完成的 session。"""
        session_dir = Path(session_dir)
        if not session_dir.exists():
            return []

        unfinished = []
        for f in sorted(session_dir.glob("session_*.json")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                questions = data.get("questions", [])
                pending = [
                    q for q in questions
                    if q["status"] not in (QuestionStatus.COMPLETED.value,)
                ]
                if pending:
                    unfinished.append({
                        "session_id": data["session_id"],
                        "subject": data.get("subject", "未知"),
                        "start_time": data.get("start_time", ""),
                        "total": len(questions),
                        "done": len(questions) - len(pending),
                        "pending": len(pending),
                    })
            except (json.JSONDecodeError, KeyError):
                pass
        return unfinished
