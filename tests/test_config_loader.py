"""M9 回归：agent_prompt.json 的 mtime 必须参与 load_config 缓存键。"""
import json
import os
import time

import pytest

from core.config_loader import clear_config_cache, load_config


@pytest.fixture
def subject_dir(tmp_path):
    with open(tmp_path / "config.json", "w", encoding="utf-8") as f:
        json.dump({"question_prompt_lines": ["题"]}, f, ensure_ascii=False)
    return str(tmp_path)


def _write_agent_prompt(subject_dir, lines):
    path = os.path.join(subject_dir, "agent_prompt.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"agent_prompt_lines": lines}, f, ensure_ascii=False)
    # 确保 mtime 一定前进，避免同一秒内写入导致缓存键未变化
    now = time.time()
    os.utime(path, (now + 1, now + 1))


def test_agent_prompt_change_invalidates_cache(subject_dir):
    try:
        _write_agent_prompt(subject_dir, ["旧版本"])
        first = load_config(subject_dir)
        assert first["agent_prompt_lines"] == ["旧版本"]

        _write_agent_prompt(subject_dir, ["新版本"])
        second = load_config(subject_dir)
        assert second["agent_prompt_lines"] == ["新版本"]
    finally:
        clear_config_cache()
