"""Issue 020：core/base_subject.py 基类测试

验证零差异方法在继承后的行为正确性。
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.base_subject import BaseSubjectApp


class _MinimalSubject(BaseSubjectApp):
    """最小化测试用学科，仅覆盖必须定义的抽象部分。"""
    LEVEL = "测试"
    SUBJECT = "测试学科"
    name = "测试学科"
    version = "v3.0"

    def build_tools(self):
        return []

    def get_max_tool_loops(self):
        return 0

    def get_tool_instructions(self):
        return ""

    def get_question_prompt(self):
        return "测试 prompt"

    def get_knowledge_prompt(self):
        return "测试知识 prompt"

    def get_review_prompt(self):
        return "测试批注 prompt"

    def split_lecture(self, md_file, output_root, base_name, options):
        pass

    def split_exam(self, md_file, output_root, base_name, options=None):
        pass

    def proofread_one(self, *args, **kwargs):
        pass


class _HistorySubject(_MinimalSubject):
    """模拟高中历史：关闭知识提取选项 + 保留粗体文本。"""
    _show_knowledge_option = False
    _clean_bold_replacement = r"\1"  # 历史保留粗体内容


@pytest.fixture
def subject_dir():
    """创建临时学科目录（含最小 config.json）。"""
    tmp = tempfile.mkdtemp()
    config = {
        "question_prompt_lines": ["测试提示词"],
        "knowledge_prompt_lines": ["测试知识提示词"],
        "lecture_split": {"wrapped_patterns": [], "unwrapped_patterns": [], "section_boundary": ""},
        "exam_split": {"question_pattern": r"^\d+[.)]"},
    }
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)
    yield tmp
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestBaseSubject:
    """验证基类零差异方法。"""

    def test_generate_knowledge_noop(self, subject_dir):
        """generate_knowledge 在 section 模式下为 no-op（ADR-0017 决策3）。"""
        with patch("core.base_subject.default_generate_knowledge") as mock:
            app = _MinimalSubject(subject_dir)
            result = app.generate_knowledge("test.md", "/out", "base")
            mock.assert_not_called()
            assert result is False

    def test_collect_paper_dirs_delegates(self, subject_dir):
        """collect_paper_dirs 应委托给 default_collect_paper_dirs。"""
        with patch("core.base_subject.default_collect_paper_dirs") as mock:
            app = _MinimalSubject(subject_dir)
            app.collect_paper_dirs("/base")
            mock.assert_called_once_with("/base")

    def test_post_proofread_hook_pass_through(self, subject_dir):
        """post_proofread_hook 默认应原样返回 result。"""
        app = _MinimalSubject(subject_dir)
        assert app.post_proofread_hook("result", "/q_dir") == "result"

    def test_pre_proofread_hook_pass_through(self, subject_dir):
        """pre_proofread_hook 默认应原样返回 md_text。"""
        app = _MinimalSubject(subject_dir)
        assert app.pre_proofread_hook("text") == "text"

    def test_get_ui_features_default(self, subject_dir):
        """get_ui_features 应返回标准字典。"""
        app = _MinimalSubject(subject_dir)
        features = app.get_ui_features()
        assert features["show_knowledge_option"] is False  # 统一模型下默认隐藏
        assert features["show_pdf_option"] is True
        assert features["show_parallel_option"] is True
        assert "试卷" in features["show_source_modes"]

    def test_get_ui_features_show_knowledge_override(self, subject_dir):
        """覆盖 _show_knowledge_option 应生效。"""
        app = _HistorySubject(subject_dir)
        features = app.get_ui_features()
        assert features["show_knowledge_option"] is False

    def test_get_supported_file_types(self, subject_dir):
        """get_supported_file_types 应返回标准文件类型列表。"""
        app = _MinimalSubject(subject_dir)
        types = app.get_supported_file_types()
        assert len(types) >= 2
        assert any("*.md" in t[1] for t in types)

    def test_get_supported_extensions(self, subject_dir):
        """get_supported_extensions 应返回标准扩展名集合。"""
        app = _MinimalSubject(subject_dir)
        exts = app.get_supported_extensions()
        assert ".md" in exts
        assert ".docx" in exts

    def test_react_mode_property(self, subject_dir):
        """react_mode 应为 property，设置时重建 tools。"""
        app = _MinimalSubject(subject_dir)
        assert app.react_mode is False
        # 设置 react_mode 应触发 build_tools
        with patch.object(app, 'build_tools', wraps=app.build_tools) as mock_build:
            app.react_mode = True
            assert app.react_mode is True
            mock_build.assert_called_once()
