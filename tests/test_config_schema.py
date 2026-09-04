"""ADR-0012 Issue 6 + ADR-00XX：配置 Schema 验证测试

question_prompt_lines 回退机制已移除（ADR-00XX），agent_prompt.json 为提示词唯一来源：
- config.json 不再要求 question_prompt_lines
- agent_prompt.json 缺失/非法即中断加载（fail-fast）
"""
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


def _write_agent_prompt(d: Path, lines):
    with open(d / "agent_prompt.json", "w", encoding="utf-8") as f:
        json.dump({"agent_prompt_lines": lines}, f, ensure_ascii=False)


class TestConfigSchema:
    """验证配置 Schema 校验。"""

    def _write_config(self, d: Path, data: dict):
        with open(d / "config.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_valid_config_passes(self, config_dir):
        """合法配置（无 question_prompt_lines）应通过校验。"""
        self._write_config(config_dir, {
            "lecture_split": {"wrapped_patterns": [], "unwrapped_patterns": []},
            "exam_split": {"question_pattern": r"^\d+[.)]"},
        })
        _write_agent_prompt(config_dir, ["题目提示词"])
        result = validate_config(config_dir)
        assert result is not None
        assert result["agent_prompt_lines"] == ["题目提示词"]
        assert "question_prompt_lines" not in result

    def test_missing_agent_prompt_file_raises(self, config_dir):
        """缺少 agent_prompt.json 应报错（提示词唯一来源，fail-fast）。"""
        self._write_config(config_dir, {})
        with pytest.raises(ValueError, match="agent_prompt.json"):
            validate_config(config_dir)

    def test_wrong_type_raises(self, config_dir):
        """agent_prompt_lines 类型错误应报错。"""
        self._write_config(config_dir, {})
        with open(config_dir / "agent_prompt.json", "w", encoding="utf-8") as f:
            json.dump({"agent_prompt_lines": "应该是数组不是字符串"}, f, ensure_ascii=False)
        with pytest.raises(ValueError, match="必须是字符串数组"):
            validate_config(config_dir)

    def test_empty_prompt_lines_raises(self, config_dir):
        """空 agent_prompt_lines 数组应报错。"""
        self._write_config(config_dir, {})
        _write_agent_prompt(config_dir, [])
        with pytest.raises(ValueError, match="不能为空"):
            validate_config(config_dir)

    def test_missing_optional_lecture_split_ok(self, config_dir):
        """可选字段缺失不报错，使用默认值。"""
        self._write_config(config_dir, {})
        _write_agent_prompt(config_dir, ["题"])
        result = validate_config(config_dir)
        assert result["lecture_wrapped_patterns"] == []

    def test_error_message_mentions_file(self, config_dir):
        """错误信息应包含提示词文件名。"""
        self._write_config(config_dir, {
        })
        with pytest.raises(ValueError) as exc:
            validate_config(config_dir)
        assert "agent_prompt.json" in str(exc.value)

    def test_config_with_knowledge_agent(self, config_dir):
        """含 knowledge_agent_prompt_lines 的配置应通过。"""
        self._write_config(config_dir, {
            "knowledge_agent_prompt_lines": ["知识 agent prompt"],
        })
        _write_agent_prompt(config_dir, ["题"])
        result = validate_config(config_dir)
        assert "knowledge_agent_prompt_lines" in result

    def test_knowledge_agent_prompt_lines_element_non_str_raises(self, config_dir):
        """M9：knowledge_agent_prompt_lines 元素必须是 str"""
        self._write_config(config_dir, {
            "knowledge_agent_prompt_lines": [123],
        })
        _write_agent_prompt(config_dir, ["题"])
        with pytest.raises(ValueError, match="元素必须是字符串"):
            validate_config(config_dir)

    def test_agent_prompt_lines_element_non_str_raises(self, config_dir):
        """M9：agent_prompt.json 的 agent_prompt_lines 元素必须是 str"""
        self._write_config(config_dir, {})
        with open(config_dir / "agent_prompt.json", "w", encoding="utf-8") as f:
            json.dump({"agent_prompt_lines": [123]}, f, ensure_ascii=False)
        with pytest.raises(ValueError, match="agent_prompt_lines.*元素必须是字符串"):
            validate_config(config_dir)