"""ADR-0012 Issue 6：配置 Schema 验证测试"""
import json
import tempfile
from pathlib import Path

import pytest

from core.config_schema import validate_config


@pytest.fixture
def config_dir():
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestConfigSchema:
    """验证配置 Schema 校验。"""

    def _write_config(self, d: Path, data: dict):
        with open(d / "config.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_valid_config_passes(self, config_dir):
        """合法配置应通过校验。"""
        self._write_config(config_dir, {
            "question_prompt_lines": ["题目提示词"],
            "lecture_split": {"wrapped_patterns": [], "unwrapped_patterns": []},
            "exam_split": {"question_pattern": r"^\d+[.)]"},
        })
        result = validate_config(config_dir)
        assert result is not None
        assert result["question_prompt_lines"] == ["题目提示词"]

    def test_missing_required_field_raises(self, config_dir):
        """缺少必填字段应报错。"""
        self._write_config(config_dir, {
        })
        with pytest.raises(ValueError, match="question_prompt_lines"):
            validate_config(config_dir)

    def test_wrong_type_raises(self, config_dir):
        """字段类型错误应报错。"""
        self._write_config(config_dir, {
            "question_prompt_lines": "应该是数组不是字符串",
        })
        with pytest.raises(ValueError):
            validate_config(config_dir)

    def test_empty_prompt_lines_raises(self, config_dir):
        """空提示词数组应报错。"""
        self._write_config(config_dir, {
            "question_prompt_lines": [],
        })
        with pytest.raises(ValueError):
            validate_config(config_dir)

    def test_missing_optional_lecture_split_ok(self, config_dir):
        """可选字段缺失不报错，使用默认值。"""
        self._write_config(config_dir, {
            "question_prompt_lines": ["题"],
        })
        result = validate_config(config_dir)
        assert result["lecture_wrapped_patterns"] == []

    def test_error_message_mentions_file(self, config_dir):
        """错误信息应包含文件名和具体字段。"""
        self._write_config(config_dir, {
        })
        with pytest.raises(ValueError) as exc:
            validate_config(config_dir)
        assert "question_prompt_lines" in str(exc.value)
        assert "config.json" in str(exc.value)

    def test_config_with_knowledge_agent(self, config_dir):
        """含 knowledge_agent_prompt_lines 的配置应通过。"""
        self._write_config(config_dir, {
            "question_prompt_lines": ["题"],
            "knowledge_agent_prompt_lines": ["知识 agent prompt"],
        })
        result = validate_config(config_dir)
        assert "knowledge_agent_prompt_lines" in result
