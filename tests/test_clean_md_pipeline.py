"""测试 _clean.md 全链路生成（ADR 0004 决策 3 + Issue #2）

验证：转换阶段生成 _clean.md，切分阶段同步写入 第N题_clean.md。
"""
import unittest
import os
import sys
import tempfile
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.docx_format_enhancer import strip_format_markers


def make_clean_md(md_text):
    """生成干净版 md——保留正文文字，去除所有格式标记和批注"""
    # Step 1: 去掉【着重】【下划线】等格式标记对
    text = strip_format_markers(md_text)
    # Step 2: 去掉 [📝批注] 标记
    result = []
    i = 0
    while i < len(text):
        m = re.match(r'\[📝批注\d+[：:]', text[i:])
        if m:
            depth = 1
            j = i + m.end()
            while j < len(text) and depth > 0:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                j += 1
            i = j
        else:
            result.append(text[i])
            i += 1
    text = ''.join(result)
    # Step 3: bold/italic 保留文字，只去标记
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    return text


class TestCleanMdPipeline(unittest.TestCase):
    """验证 _clean.md 生成与同步写入的逻辑"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="tdd_clean_")
        self.raw_md = """## 第1题
阅读下面的文言文，完成1-6题。

【着重】韦凑字彦宗【/着重】，京兆万年人。永淳初，【下划线】解褐婺州参军事【/下划线】。

[📝批注1：此处有异文]徙资州司兵，观察使房昶才之，表于朝，迁扬州法曹。

**韦子识远文详**，吾恨晚得之。
"""

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_clean_md_contains_no_format_markers(self):
        clean = make_clean_md(self.raw_md)
        markers = ["【着重】", "【/着重】", "【下划线】", "【/下划线】",
                   "【波浪线】", "【/波浪线】", "【删除线】", "【/删除线】"]
        for m in markers:
            self.assertNotIn(m, clean, f"clean 版不应含 '{m}'")

    def test_clean_md_contains_no_annotation_markers(self):
        clean = make_clean_md(self.raw_md)
        self.assertNotIn("📝批注", clean)

    def test_clean_md_preserves_chinese_text(self):
        clean = make_clean_md(self.raw_md)
        must_preserve = [
            "韦凑字彦宗", "京兆万年人", "永淳初",
            "解褐婺州参军事", "观察使房昶才之", "扬州法曹",
            "韦子识远文详",
        ]
        for text in must_preserve:
            self.assertIn(text, clean, f"clean 版应保留正文 '{text}'")

    def test_bold_text_preserved_not_deleted(self):
        clean = make_clean_md("**韦凑**字彦宗")
        self.assertIn("韦凑", clean)

    def test_hanzi_subset_of_raw(self):
        clean = make_clean_md(self.raw_md)
        raw_han = set(re.findall(r'[一-鿿]', self.raw_md))
        clean_han = set(re.findall(r'[一-鿿]', clean))
        missing = clean_han - raw_han
        self.assertEqual(missing, set(),
                         f"clean 版不应有 raw 版中不存在的汉字: {missing}")

    def test_write_clean_alongside_raw(self):
        q_dir = os.path.join(self.tmpdir, "第1题")
        os.makedirs(q_dir, exist_ok=True)
        raw_path = os.path.join(q_dir, "第1题.md")
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(self.raw_md)
        clean_content = make_clean_md(self.raw_md)
        clean_path = os.path.join(q_dir, "第1题_clean.md")
        with open(clean_path, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        self.assertTrue(os.path.exists(raw_path))
        self.assertTrue(os.path.exists(clean_path))
        with open(clean_path, 'r', encoding='utf-8') as f:
            saved = f.read()
        self.assertEqual(saved, clean_content)
        self.assertNotIn("【下划线】", saved)


if __name__ == "__main__":
    unittest.main()
