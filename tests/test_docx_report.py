import base64
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.docx_report import generate_combined_docx
from core.pandoc_utils import find_pandoc

_1PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

REPORT_WITH_MARKS = """# 第1题 校对报告

轻微问题

### 标记原文
编号：第1题
内容：
1．下列关于物理量的说法正确的是（　　）

【1|电荷量很小的电荷就是元电荷|元电荷是最小的电荷量，并非电荷量很小的电荷】

【2|电量|电荷量】是电荷的多少

![@@@testuuid00000000000000000000000001](./images/img1.png){width="1.0in" height="0.8in"}

### 修改原因
1. 元电荷是最小的电荷量，表述不严谨。
2. "电量"为口语化表述，应规范为"电荷量"。
"""

REPORT_NO_MARKS = """# 第2题 校对报告

无问题

### 标记原文
编号：第2题
内容：
2．下列说法正确的是（　　）

A．正确

B．错误

### 修改原因
无
"""


class TestGenerateCombinedDocx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_report_test_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        os.makedirs(os.path.join(self.paper, "第1题", "images"))
        os.makedirs(os.path.join(self.paper, "第2题"))
        with open(os.path.join(self.paper, "第1题", "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_WITH_MARKS)
        with open(os.path.join(self.paper, "第2题", "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_NO_MARKS)
        with open(os.path.join(self.paper, "第1题", "images", "img1.png"), "wb") as f:
            f.write(_1PX_PNG)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generate_combined_docx(self):
        out_dir = os.path.join(self.tmp, "out")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        self.assertTrue(os.path.exists(docx_path))

        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        ET.fromstring(doc)
        ET.fromstring(cmt)

        n_cmt = len(self._findall(cmt, "<w:comment w:id="))
        n_start = len(self._findall(doc, "<w:commentRangeStart"))
        n_end = len(self._findall(doc, "<w:commentRangeEnd"))
        n_ref = len(self._findall(doc, "<w:commentReference"))
        self.assertEqual(n_cmt, 2)
        self.assertEqual(n_start, n_end)
        self.assertEqual(n_end, n_ref)
        self.assertEqual(n_ref, n_cmt)

    def test_no_caption_and_no_uuid(self):
        out_dir = os.path.join(self.tmp, "out2")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertNotIn("CaptionedFigure", doc)
        self.assertNotIn("@@@", doc)

    def test_image_embedded_and_renamed(self):
        out_dir = os.path.join(self.tmp, "out3")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertGreaterEqual(doc.count("<w:drawing>"), 1)
        media = [n for n in z.namelist() if n.startswith("word/media/")]
        self.assertTrue(media)

    def test_headings_and_page_breaks(self):
        out_dir = os.path.join(self.tmp, "out4")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertEqual(len(self._findall(doc, 'w:val="Heading1"')), 2)
        self.assertGreaterEqual(len(self._findall(doc, 'w:type="page"')), 1)

    def test_empty_dir_returns_none(self):
        empty = os.path.join(self.tmp, "空目录")
        os.makedirs(empty)
        self.assertIsNone(generate_combined_docx(empty, self.tmp))

    @staticmethod
    def _findall(text, needle):
        return [m for m in range(len(text)) if text.startswith(needle, m)]


if __name__ == "__main__":
    unittest.main()
