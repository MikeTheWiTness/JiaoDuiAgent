import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.docx_comments import (
    parse_comments_xml,
    extract_comment_anchors,
    insert_comments_into_md,
    normalize_text,
    fuzzy_insert_comment,
)


class TestParseCommentsXml(unittest.TestCase):
    def test_single_comment(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="张三" w:date="2026-01-01T00:00:00Z" w:initials="">
    <w:p>
      <w:r><w:t>这是第一条批注</w:t></w:r>
    </w:p>
  </w:comment>
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments["0"], "这是第一条批注")

    def test_multiple_comments(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="A">
    <w:p><w:r><w:t>批注一</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="1" w:author="B">
    <w:p><w:r><w:t>批注二</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="2" w:author="C">
    <w:p><w:r><w:t>批注三</w:t></w:r></w:p>
  </w:comment>
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertEqual(len(comments), 3)
        self.assertEqual(comments["0"], "批注一")
        self.assertEqual(comments["1"], "批注二")
        self.assertEqual(comments["2"], "批注三")

    def test_comment_with_multiple_runs(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="A">
    <w:p>
      <w:r><w:t>第一段</w:t></w:r>
      <w:r><w:t>第二段</w:t></w:r>
    </w:p>
  </w:comment>
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertIn("第一段", comments["0"])
        self.assertIn("第二段", comments["0"])

    def test_empty_comments(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertEqual(comments, {})


class TestExtractCommentAnchors(unittest.TestCase):
    def test_single_anchor(self):
        doc_xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>前面文字</w:t></w:r>
      <w:commentRangeStart w:id="0"/>
      <w:r><w:t>锚定文本</w:t></w:r>
      <w:commentRangeEnd w:id="0"/>
      <w:r><w:commentReference w:id="0"/></w:r>
      <w:r><w:t>后面文字</w:t></w:r>
    </w:p>
  </w:body>
</w:document>'''
        anchors = extract_comment_anchors(doc_xml)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0]["id"], "0")
        self.assertEqual(anchors[0]["text"], "锚定文本")

    def test_multiple_anchors(self):
        doc_xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:commentRangeStart w:id="0"/>
      <w:r><w:t>第一个锚点</w:t></w:r>
      <w:commentRangeEnd w:id="0"/>
      <w:r><w:commentReference w:id="0"/></w:r>
      <w:r><w:t>中间</w:t></w:r>
      <w:commentRangeStart w:id="1"/>
      <w:r><w:t>第二个锚点</w:t></w:r>
      <w:commentRangeEnd w:id="1"/>
      <w:r><w:commentReference w:id="1"/></w:r>
    </w:p>
  </w:body>
</w:document>'''
        anchors = extract_comment_anchors(doc_xml)
        self.assertEqual(len(anchors), 2)
        self.assertEqual(anchors[0]["id"], "0")
        self.assertEqual(anchors[0]["text"], "第一个锚点")
        self.assertEqual(anchors[1]["id"], "1")
        self.assertEqual(anchors[1]["text"], "第二个锚点")

    def test_no_anchors(self):
        doc_xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>纯文本无批注</w:t></w:r></w:p></w:body>
</w:document>'''
        anchors = extract_comment_anchors(doc_xml)
        self.assertEqual(anchors, [])


class TestInsertCommentsIntoMd(unittest.TestCase):
    def test_single_comment_insertion(self):
        md = "这是一段文字，其中有个错别字。"
        comments = {"0": "应该是'错别宇'吗？不对，应该是'错别字'才对"}
        anchors = [{"id": "0", "text": "错别字"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertIn('<批注 id=1>', result)
        self.assertIn("错别字", result)

    def test_multiple_comments(self):
        md = "春天来了，花儿开了，小鸟在树上唱歌。"
        comments = {"0": "是'春天'还是'春季'？", "1": "应该是'鸟儿'吧"}
        anchors = [{"id": "0", "text": "春天"}, {"id": "1", "text": "小鸟"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertIn("批注 id=1", result)
        self.assertIn("批注 id=2", result)

    def test_no_comments_returns_original(self):
        md = "纯文本没有批注"
        comments = {}
        anchors = []
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)

    def test_anchor_not_found_skip(self):
        md = "这段文字里找不到锚点"
        comments = {"0": "这条批注找不到位置"}
        anchors = [{"id": "0", "text": "不存在的文本"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)


class TestExtractCommentsToMd(unittest.TestCase):
    def test_function_exists(self):
        from shared.docx_comments import extract_comments_to_md
        self.assertTrue(callable(extract_comments_to_md))

    def test_nonexistent_file_returns_false(self):
        from shared.docx_comments import extract_comments_to_md
        import tempfile
        result = extract_comments_to_md("/nonexistent/path.docx", "/tmp/out.md")
        self.assertFalse(result)


class TestEdgeCases(unittest.TestCase):
    def test_comment_id_not_in_dict_skipped(self):
        md = "正文内容"
        comments = {"99": "这条批注没有对应锚点"}
        anchors = [{"id": "0", "text": "不存在"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)

    def test_anchor_with_empty_text_skipped(self):
        md = "正文"
        comments = {"0": "空锚点批注"}
        anchors = [{"id": "0", "text": ""}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)

    def test_multiple_occurrences_only_first(self):
        md = "苹果香蕉苹果橙子苹果"
        comments = {"0": "第一个苹果的批注"}
        anchors = [{"id": "0", "text": "苹果"}]
        result = insert_comments_into_md(md, comments, anchors)
        count = result.count("批注 id=1")
        self.assertEqual(count, 1)

    def test_comment_numbering_sequential(self):
        md = "甲乙丙丁"
        comments = {"0": "批注A", "1": "批注B", "2": "批注C"}
        anchors = [
            {"id": "0", "text": "甲"},
            {"id": "1", "text": "乙"},
            {"id": "2", "text": "丙"},
        ]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertIn("批注 id=1", result)
        self.assertIn("批注 id=2", result)
        self.assertIn("批注 id=3", result)


class TestNormalizeText(unittest.TestCase):
    def test_remove_all_whitespace(self):
        self.assertEqual(normalize_text("a b  c\n\nd"), "abcd")

    def test_chinese_quotes_to_english(self):
        self.assertEqual(normalize_text("“选非”"), '"选非"')

    def test_mixed_whitespace_and_quotes(self):
        self.assertEqual(normalize_text("“你好   世界”\n"), '"你好世界"')

    def test_empty_string(self):
        self.assertEqual(normalize_text(""), "")

    def test_only_whitespace(self):
        self.assertEqual(normalize_text("   \n\t  "), "")


class TestFuzzyInsertComment(unittest.TestCase):
    def test_exact_match(self):
        md = "这是正文内容"
        result, ok = fuzzy_insert_comment(md, "正文", "批注内容", 1)
        self.assertTrue(ok)
        self.assertIn('<批注 id=1><原>正文</原><改>批注内容</改></批注>', result)

    def test_newline_difference(self):
        md = "这是正\n文内容"
        result, ok = fuzzy_insert_comment(md, "正文", "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_quote_difference(self):
        md = '一般以"选非"的形式考查'
        result, ok = fuzzy_insert_comment(md, "“选非”", "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_three_spaces_to_newlines(self):
        md = "参考含义：精神\n\n原因：作者\n\n情感：赞美"
        anchor = "参考含义：精神   原因：作者   情感：赞美"
        result, ok = fuzzy_insert_comment(md, anchor, "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_paragraph_break_in_answer(self):
        md = "2.【试题答案】B\n\n【试题考点】本题考查\n\n【试题解析】解析内容"
        anchor = "2.【试题答案】B【试题考点】本题考查【试题解析】解析内容"
        result, ok = fuzzy_insert_comment(md, anchor, "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_no_match_returns_false(self):
        md = "完全不相关的文本"
        result, ok = fuzzy_insert_comment(md, "找不到的锚点", "批注", 1)
        self.assertFalse(ok)
        self.assertEqual(result, md)


if __name__ == "__main__":
    unittest.main()
