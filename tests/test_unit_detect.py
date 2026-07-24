"""测试 core/unit_detect.py 目录识别逻辑（ADR-0022 C2.3）。"""
import tempfile
from pathlib import Path

import pytest

from core.unit_detect import is_unit_dir, scan_question_dirs


class TestIsUnitDir:
    def test_question_dir(self):
        assert is_unit_dir("第1题")

    def test_question_dir_multi_digit(self):
        assert is_unit_dir("第12题")

    def test_section_dir(self):
        assert is_unit_dir("板块1")

    def test_unit_dir(self):
        assert is_unit_dir("单元1")

    def test_unit_dir_multi_digit(self):
        assert is_unit_dir("单元12")

    def test_non_matching_dir(self):
        assert not is_unit_dir("知识")

    def test_non_matching_empty(self):
        assert not is_unit_dir("")

    def test_question_in_name_anywhere(self):
        assert is_unit_dir("第1题_备份")


class TestScanQuestionDirs:
    def test_first_level_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "第1题").mkdir()
            (root / "第2题").mkdir()
            result = scan_question_dirs(root)
            assert len(result) == 1
            assert str(result[0]) == str(root)

    def test_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "其他").mkdir()
            result = scan_question_dirs(root)
            assert len(result) == 0

    def test_knowledge_dir_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "知识").mkdir()
            result = scan_question_dirs(root)
            assert len(result) == 1

    def test_second_level_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sub = root / "paper1"
            sub.mkdir()
            (sub / "第1题").mkdir()
            result = scan_question_dirs(root)
            assert len(result) == 1
            assert str(result[0]) == str(sub)
