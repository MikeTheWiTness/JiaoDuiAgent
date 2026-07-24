import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.split_post_utils import SKIP_MARKER_FILE, mark_navigation_units


class TestSkipProofreadContract(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_root = self.temp_dir.name
        self.base_name = "test_doc"

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 辅助方法 ──────────────────────────────────────────────
    def _target_dir(self):
        return Path(self.output_root) / self.base_name

    def _make_unit(self, unit_name, first_line):
        """创建包含一个 .md 文件的板块目录。"""
        unit_dir = self._target_dir() / unit_name
        unit_dir.mkdir(parents=True, exist_ok=True)
        md_file = unit_dir / "content.md"
        md_file.write_text(first_line + "\n\n正文内容……", encoding="utf-8")
        return unit_dir

    def _make_units(self, *specs):
        """批量创建板块目录。specs: (unit_name, first_line) 元组列表。"""
        for name, first_line in specs:
            self._make_unit(name, first_line)

    # ── 测试用例 ──────────────────────────────────────────────
    def test_creates_skip_marker(self):
        """匹配模式时创建 .skip_proofread 标记文件。"""
        self._make_unit("01_直击课堂", "# 直击课堂")
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 1)
        skip_file = self._target_dir() / "01_直击课堂" / SKIP_MARKER_FILE
        self.assertTrue(skip_file.exists())

    def test_marker_placed_in_unit_dir(self):
        """.skip_proofread 文件创建在正确的板块子目录中。"""
        self._make_unit("02_本讲导航", "## 本讲导航 - 内容概览")
        mark_navigation_units(self.output_root, self.base_name)
        skip_file = self._target_dir() / "02_本讲导航" / SKIP_MARKER_FILE
        self.assertTrue(skip_file.exists())
        # 确认标记文件不在上层目录
        parent_marker = self._target_dir() / SKIP_MARKER_FILE
        self.assertFalse(parent_marker.exists())

    def test_multiple_navigation_units(self):
        """多个匹配的板块都被标记。"""
        self._make_units(
            ("01_直击课堂", "# 直击课堂"),
            ("02_知识点", "## 知识点讲解"),
            ("03_本讲导航", "# 本讲导航"),
            ("04_练习", "## 练习"),
        )
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 2)
        self.assertTrue((self._target_dir() / "01_直击课堂" / SKIP_MARKER_FILE).exists())
        self.assertTrue((self._target_dir() / "03_本讲导航" / SKIP_MARKER_FILE).exists())
        self.assertFalse((self._target_dir() / "02_知识点" / SKIP_MARKER_FILE).exists())
        self.assertFalse((self._target_dir() / "04_练习" / SKIP_MARKER_FILE).exists())

    def test_non_matching_units_not_marked(self):
        """不匹配模式的板块不创建标记文件。"""
        self._make_units(
            ("01_知识点", "# 知识点一"),
            ("02_例题", "## 例题精讲"),
        )
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 0)
        self.assertFalse((self._target_dir() / "01_知识点" / SKIP_MARKER_FILE).exists())
        self.assertFalse((self._target_dir() / "02_例题" / SKIP_MARKER_FILE).exists())

    def test_missing_target_dir_returns_zero(self):
        """base_name 目录不存在时返回 0 且不报错。"""
        marked = mark_navigation_units(self.output_root, "nonexistent_doc")
        self.assertEqual(marked, 0)

    def test_empty_target_dir_returns_zero(self):
        """目标目录存在但无子目录时返回 0。"""
        self._target_dir().mkdir(parents=True)
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 0)

    def test_subdir_without_md_files_skipped(self):
        """子目录不含 .md 文件时跳过该目录。"""
        unit_dir = self._target_dir() / "empty_unit"
        unit_dir.mkdir(parents=True)
        # 不创建任何 .md 文件
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 0)
        self.assertFalse((unit_dir / SKIP_MARKER_FILE).exists())

    def test_custom_patterns(self):
        """自定义模式生效。"""
        self._make_units(
            ("封面", "# 课程封面"),
            ("目录", "## 目录"),
        )
        marked = mark_navigation_units(
            self.output_root, self.base_name,
            patterns=[r"封面", r"目录"],
        )
        self.assertEqual(marked, 2)
        self.assertTrue((self._target_dir() / "封面" / SKIP_MARKER_FILE).exists())
        self.assertTrue((self._target_dir() / "目录" / SKIP_MARKER_FILE).exists())

    def test_partial_match_in_first_line(self):
        """首行包含模式子串即匹配。"""
        self._make_unit("01_开场", "### 直击课堂 - 今日要点")
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 1)
        self.assertTrue((self._target_dir() / "01_开场" / SKIP_MARKER_FILE).exists())

    def test_return_value_is_int(self):
        """返回值是整数类型。"""
        self._make_unit("nav", "# 直击课堂")
        result = mark_navigation_units(self.output_root, self.base_name)
        self.assertIsInstance(result, int)


if __name__ == "__main__":
    unittest.main()
