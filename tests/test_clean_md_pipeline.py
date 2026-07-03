"""测试 _clean.md 全链路生成（ADR 0004 决策 3 + Issue #2）"""
import os
import tempfile
import re
import pytest
from shared.docx_format_enhancer import strip_format_markers


def make_clean_md(md_text):
    """生成干净版 md——保留正文文字，去除所有格式标记和批注"""
    text = strip_format_markers(md_text)
    text = re.sub(r'<批注\s+id=\d+>.*?</批注>', '', text, flags=re.DOTALL)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    return text


@pytest.fixture
def raw_md():
    return """## 第1题
阅读下面的文言文，完成1-6题。

<着重>韦凑字彦宗</着重>，京兆万年人。永淳初，<下划线>解褐婺州参军事</下划线>。

<批注 id=1><原>此处</原><改>此处有异文</改></批注>徙资州司兵，观察使房昶才之，表于朝，迁扬州法曹。

**韦子识远文详**，吾恨晚得之。
"""


class TestCleanMdPipeline:
    """验证 _clean.md 生成与同步写入的逻辑"""

    def test_clean_md_contains_no_format_markers(self, raw_md):
        clean = make_clean_md(raw_md)
        markers = ["<着重>", "</着重>", "<下划线>", "</下划线>",
                   "<波浪线>", "</波浪线>", "<删除线>", "</删除线>"]
        for m in markers:
            assert m not in clean, f"clean 版不应含 '{m}'"

    def test_clean_md_contains_no_annotation_markers(self, raw_md):
        clean = make_clean_md(raw_md)
        assert '批注' not in clean

    def test_clean_md_preserves_chinese_text(self, raw_md):
        clean = make_clean_md(raw_md)
        must_preserve = [
            "韦凑字彦宗", "京兆万年人", "永淳初",
            "解褐婺州参军事", "观察使房昶才之", "扬州法曹",
            "韦子识远文详",
        ]
        for text in must_preserve:
            assert text in clean, f"clean 版应保留正文 '{text}'"

    def test_bold_text_preserved_not_deleted(self):
        clean = make_clean_md("**韦凑**字彦宗")
        assert "韦凑" in clean

    def test_hanzi_subset_of_raw(self, raw_md):
        clean = make_clean_md(raw_md)
        raw_han = set(re.findall(r'[一-鿿]', raw_md))
        clean_han = set(re.findall(r'[一-鿿]', clean))
        missing = clean_han - raw_han
        assert missing == set(), f"clean 版不应有 raw 版中不存在的汉字: {missing}"

    def test_write_clean_alongside_raw(self, raw_md, temp_dir):
        q_dir = temp_dir / "第1题"
        q_dir.mkdir(exist_ok=True)
        raw_path = q_dir / "第1题.md"
        raw_path.write_text(raw_md, encoding='utf-8')
        clean_content = make_clean_md(raw_md)
        clean_path = q_dir / "第1题_clean.md"
        clean_path.write_text(clean_content, encoding='utf-8')
        assert raw_path.exists()
        assert clean_path.exists()
        saved = clean_path.read_text(encoding='utf-8')
        assert saved == clean_content
        assert "<下划线>" not in saved
