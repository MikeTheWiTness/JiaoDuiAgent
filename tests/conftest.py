"""共享 pytest fixtures。"""
import tempfile
import json
import os
from pathlib import Path
import pytest


@pytest.fixture
def temp_dir():
    """创建临时目录，测试结束后自动清理。"""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def temp_config_dir(temp_dir):
    """创建含最小 config.json 的临时学科目录。"""
    config = {
        "question_prompt_lines": ["测试提示词"],
        "knowledge_prompt_lines": ["测试知识提示词"],
        "lecture_split": {"wrapped_patterns": [], "unwrapped_patterns": [], "section_boundary": ""},
        "exam_split": {"question_pattern": r"^\d+[.)]"},
    }
    with open(temp_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)
    return temp_dir
