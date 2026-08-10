import base64
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest import mock

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

    def test_relative_out_dir_resolved_to_absolute(self):
        """回归：相对 out_dir 时 docx 必须落到调用方 cwd 下且返回绝对路径。

        修复前：pandoc 以临时工作目录为 cwd，相对 out_dir 把 docx 写进临时目录
        （finally 即删），_inject_comments 按调用方 cwd 打开相对路径抛
        FileNotFoundError，generate_combined_docx 捕获后返回 None。
        """
        old_cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            docx_path = generate_combined_docx(self.paper, "output/校对Word")
            self.assertIsNotNone(docx_path)
            self.assertTrue(os.path.isabs(docx_path))
            self.assertTrue(os.path.exists(docx_path))
            # 文件必须真实落在 out_dir 对应的相对位置，而非漂移到 pandoc 临时目录
            rel = os.path.join("output", "校对Word", os.path.basename(docx_path))
            self.assertTrue(os.path.exists(rel))
            z = zipfile.ZipFile(docx_path)
            cmt = z.read("word/comments.xml").decode("utf-8")
            self.assertEqual(len(self._findall(cmt, "<w:comment w:id=")), 2)
        finally:
            os.chdir(old_cwd)

    @staticmethod
    def _findall(text, needle):
        return [m for m in range(len(text)) if text.startswith(needle, m)]


class TestSkippedUnitsDiagnostics(unittest.TestCase):
    """回归：无分段跳过必须区分「无批注（正常）」与「含标记但缺分段（可疑）」。

    修复前：LLM 判定「无问题」的报告（只有 无问题+工具日志+思考过程，
    无 ### 标记原文/### 修改原因 分段）被统一记 ⚠️「分段异常，跳过」，
    正常业务形态被误标为异常，误导排查。
    """

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_skip_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_paper(self, units):
        """units: {目录名: 报告内容}，另加一个带批注的基准单元保证 docx 生成。"""
        paper = os.path.join(self.tmp, "测试试卷")
        for name, content in units.items():
            d = os.path.join(paper, name)
            os.makedirs(d)
            with open(os.path.join(d, "_校对报告.md"), "w", encoding="utf-8") as f:
                f.write(content)
        return paper

    NO_ISSUE_REPORT = """无问题

---

## 📋 工具调用日志

共调用 1 次

## 📋 模型思考过程（仅核查用，不出现在 PDF 中）

题目与解答均无错误。
"""

    def test_no_issue_unit_listed_as_no_issue(self):
        """「无问题」报告（无分段、无批注标记）必须列入报告并标注，不得记 ⚠️ 异常"""
        from core import docx_report
        paper = self._make_paper({
            "第1题": REPORT_WITH_MARKS,
            "单元7": self.NO_ISSUE_REPORT,
        })
        with mock.patch.object(docx_report, "log") as mlog:
            docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        messages = [c.args[0] for c in mlog.call_args_list]
        self.assertTrue(any("单元7 无批注，列入报告" in m for m in messages))
        self.assertFalse(any("分段异常" in m or "含批注标记" in m for m in messages))
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 无批注单元出现在报告里（独立标题 + 无问题标注），不产生批注
        self.assertEqual(len(self._findall(doc, 'w:val="Heading1"')), 2)
        self.assertIn("无问题", doc)
        self.assertEqual(cmt.count("<w:comment w:id="), 2)

    def test_all_no_issue_units_still_generate_report(self):
        """整份试卷全部无问题也必须生成报告（标注无问题），不得返回 None"""
        paper = self._make_paper({
            "单元7": self.NO_ISSUE_REPORT,
            "单元9": self.NO_ISSUE_REPORT,
        })
        docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out_noissue"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertEqual(len(self._findall(doc, 'w:val="Heading1"')), 2)
        self.assertEqual(doc.count("无问题"), 2)

    def test_url_image_ref_replaced_with_text(self):
        """外链 https:// 图片引用（LLM 幻觉）转为文字说明，不得重写成垃圾本地路径"""
        from core import docx_report
        url_report = REPORT_WITH_MARKS.replace(
            "![@@@testuuid00000000000000000000000001](./images/img1.png)",
            "![外链图](https://p3-hippo-sign.example.com/x/y.png?lk3s=19ff00fe&x-expires=2067)")
        paper = self._make_paper({"第1题": url_report})
        with mock.patch.object(docx_report, "log") as mlog:
            docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out_url"))
        self.assertIsNotNone(docx_path)
        messages = [c.args[0] for c in mlog.call_args_list]
        self.assertFalse(any("图片未找到" in m for m in messages))
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertIn("外链图片无法嵌入", doc)
        self.assertNotIn("p3-hippo-sign", doc)
        self.assertNotIn("lk3s=", doc)

    @staticmethod
    def _findall(text, needle):
        return [m for m in range(len(text)) if text.startswith(needle, m)]

    def test_marked_without_sections_warns_and_skips(self):
        """含 【N|原|改】 标记但缺分段 → ⚠️ 警告（批注可能丢失）且该单元跳过"""
        from core import docx_report
        paper = self._make_paper({
            "第1题": REPORT_WITH_MARKS,
            "单元9": "有批注标记但缺分段：【1|原句|改为句】\n",
        })
        with mock.patch.object(docx_report, "log") as mlog:
            docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out2"))
        self.assertIsNotNone(docx_path)
        messages = [c.args[0] for c in mlog.call_args_list]
        self.assertTrue(any("单元9 含批注标记但缺少" in m for m in messages))
        # 该单元被跳过：批注仍只来自第1题
        z = zipfile.ZipFile(docx_path)
        cmt = z.read("word/comments.xml").decode("utf-8")
        self.assertEqual(cmt.count("<w:comment w:id="), 2)


class TestEscapedPipeInMarkers(unittest.TestCase):
    """回归：原文字段中的 LaTeX 转义竖线 \| 不得被当作字段分隔符。

    修复前：_PAT 按 [^|] 分割，【N|$\left\|…\right\|$|改】 的 original 在
    \| 处截断，后半截拼进 correction 还带 |，批注内容损坏。
    """

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_pipe_test_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        q = os.path.join(self.paper, "第1题")
        os.makedirs(q)
        report = (
            "# 第1题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            "总电动势【1|${E}_{总}=\\left\\|{E}_{1}-{E}_{2}\\right\\|$|"
            "${E}_{总}=\\left|{E}_{1}-{E}_{2}\\right|$】，方向与【2|大者|数值较大的电动势】一致。\n\n"
            "### 修改原因\n1. 双竖线改单竖线。\n2. 表述严谨。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_latex_pipe_not_split(self):
        """\| 转义竖线整体保留在 original，批注数正确"""
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        self.assertEqual(cmt.count("<w:comment w:id="), 2)
        # 原文公式（含 \| 双竖线）作为整体被锚定：批注范围完整包住 oMath 对象
        self.assertIn('<w:commentRangeStart w:id="1"/><m:oMath>', doc)
        self.assertIn('</m:oMath><w:commentRangeEnd w:id="1"/>', doc)
        # 双竖线符号 ∥（pandoc 将 \left\| 转为 OMML 的 begChr/endChr）保留在锚点内
        self.assertIn("∥", doc)
        # 改后（单竖线公式）写入批注内容
        self.assertIn(r"\left|{E}_{1}-{E}_{2}\right|", cmt)


class TestConvertMultilineTables(unittest.TestCase):
    """回归：_convert_multiline_tables 不得把普通 bullet 列表误判为表格。

    修复前：判定条件 startswith("-") and len>=10 把任意 10 字以上列表项
    当作 multiline table 边框，正文被按 2+ 空格切分成网格表格静默改写。
    修复后：只有「整行全部由 - 组成」的长线才是表格边框。
    """

    def setUp(self):
        from core.docx_report import _convert_multiline_tables
        self._convert = _convert_multiline_tables

    def test_bullet_list_not_treated_as_table(self):
        """两条以上 bullet 列表项必须原样保留，不得转成网格表格"""
        text = (
            "### 标记原文\n\n"
            "- 首先我们先看这道题目的已知条件是什么\n"
            "- 其次要注意单位换算关系\n"
            "- 最后检查计算过程是否合理"
        )
        out = self._convert(text)
        self.assertNotIn("|", out)
        self.assertIn("- 首先我们先看这道题目的已知条件是什么", out)
        self.assertIn("- 其次要注意单位换算关系", out)
        self.assertIn("- 最后检查计算过程是否合理", out)

    def test_single_bullet_not_treated_as_table(self):
        """单条 bullet（无配对边界）也不受影响"""
        text = "- 这是一条超过十个字符的普通列表项内容"
        out = self._convert(text)
        self.assertEqual(out, text)

    def test_real_multiline_table_still_converted(self):
        """真实 multiline table（--- 边框）仍应转为 grid table"""
        text = (
            "前文\n\n"
            "---------------\n"
            "列一  列二  列三\n"
            "甲    乙    丙\n"
            "---------------\n\n"
            "后文"
        )
        out = self._convert(text)
        self.assertIn("| 列一", out)
        self.assertIn("| 甲", out)
        self.assertIn("前文", out)
        self.assertIn("后文", out)

    def test_short_separator_untouched(self):
        """短 --- markdown 分隔线保持原样"""
        text = "正文\n\n---\n\n后续"
        out = self._convert(text)
        self.assertEqual(out, text)

    def test_empty_and_plain_text(self):
        self.assertEqual(self._convert(""), "")
        plain = "没有任何表格的普通段落。\n第二行。"
        self.assertEqual(self._convert(plain), plain)


if __name__ == "__main__":
    unittest.main()
