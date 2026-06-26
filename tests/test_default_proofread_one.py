'''测试 default_proofread_one 文件选择逻辑（ADR 0004 决策 4）

验证：当目录中有多个 .md 文件时，始终精确读取与目录同名的 .md。
本文件独立测试文件选择子逻辑，不依赖 LLM API。
'''
import unittest
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestProofreadOneFileSelection(unittest.TestCase):
    '''验证 default_proofread_one 精确匹配目录名的行为'''

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="tdd_qdir_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _qdir(self, name):
        d = os.path.join(self.tmpdir, name)
        os.makedirs(d, exist_ok=True)
        return d

    def _write(self, d, fn, body):
        with open(os.path.join(d, fn), 'w', encoding='utf-8') as f:
            f.write(body)

    # ---- 旧逻辑（当前线上代码）----

    @staticmethod
    def _read_md_old(q_dir):
        '''当前 core/defaults.py:520-527 的实现'''
        for f in os.listdir(q_dir):
            if f.endswith(".md"):
                with open(os.path.join(q_dir, f), 'r', encoding='utf-8') as fm:
                    return fm.read()
        return None

    @staticmethod
    def _read_md_new(q_dir, q_name):
        '''新实现：精确匹配 {q_name}.md'''
        target = os.path.join(q_dir, f"{q_name}.md")
        if os.path.exists(target):
            with open(target, 'r', encoding='utf-8') as fm:
                return fm.read()
        return None

    # ---- 测试 ----

    def test_old_code_reads_wrong_file_when_underscore_name_first(self):
        '''暴露旧代码 bug：下划线开头的 .md 文件在 NTFS 排序中排在前面'''
        d = self._qdir("第1题")
        # _ 开头确保在 NTFS 排序时排在「第1题.md」之前
        self._write(d, "_第1题_clean.md", "干净正文")
        self._write(d, "第1题.md", "含标记的正文")

        old = self._read_md_old(d)

        # 旧代码读到 _clean.md（bug！）
        self.assertEqual(old, "干净正文",
                         "旧代码应读到 _ 开头的 _clean.md — 这就是要修复的 bug")

    def test_new_code_always_reads_correct_file(self):
        '''新代码在有 _clean 干扰时仍读取正确的 md'''
        d = self._qdir("第1题")
        self._write(d, "_第1题_clean.md", "干净正文")
        self._write(d, "第1题.md", "含标记的正文")

        new = self._read_md_new(d, "第1题")
        self.assertEqual(new, "含标记的正文",
                         "新代码精确匹配，应读到与目录同名的 md")

    def test_reads_correct_md_when_3_md_files_exist(self):
        '''3 个 .md 共存时新逻辑读到正确的'''
        d = self._qdir("第1题")
        self._write(d, "第1题.md", "含标记的正文")
        self._write(d, "_校对报告.md", "校对结果")
        self._write(d, "_第1题_clean.md", "干净正文")

        result = self._read_md_new(d, "第1题")
        self.assertEqual(result, "含标记的正文")

    def test_single_md_still_works(self):
        '''只有一个 .md 时新旧逻辑都能读到'''
        d = self._qdir("第1题")
        self._write(d, "第1题.md", "唯一正文")

        self.assertEqual(self._read_md_old(d), "唯一正文")
        self.assertEqual(self._read_md_new(d, "第1题"), "唯一正文")

    def test_no_matching_md_returns_none(self):
        '''没有同名 .md 时返回 None'''
        d = self._qdir("第1题")
        self._write(d, "其他文件.md", "不是目标")

        result = self._read_md_new(d, "第1题")
        self.assertIsNone(result)

    def test_special_chars_in_q_name(self):
        '''q_name 含括号、空格等特殊字符'''
        name = "板块1(文言文)-基础"
        d = self._qdir(name)
        self._write(d, f"{name}.md", "板块正文")

        result = self._read_md_new(d, name)
        self.assertEqual(result, "板块正文")

    def test_only_matches_md_not_txt(self):
        '''只匹配 .md 扩展名'''
        d = self._qdir("第1题")
        self._write(d, "第1题.txt", "文本")
        self._write(d, "第1题.md", "markdown")

        result = self._read_md_new(d, "第1题")
        self.assertEqual(result, "markdown")


if __name__ == "__main__":
    unittest.main()
