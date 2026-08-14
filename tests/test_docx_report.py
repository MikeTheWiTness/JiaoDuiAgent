import base64
import os
import re
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
        self.assertTrue(any("单元7 无批注" in m for m in messages))
        self.assertFalse(any("分段异常" in m or "含批注标记" in m for m in messages))
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 无批注单元出现在报告里（独立标题 + 无问题标注），不产生批注
        self.assertEqual(len(self._findall(doc, 'w:val="Heading1"')), 2)
        self.assertIn("无问题", doc)
        self.assertEqual(cmt.count("<w:comment w:id="), 2)

    def test_no_issue_unit_with_md_inserts_original_and_comment(self):
        """无问题单元存在单元 md 时：插入原文正文，并在正文开头生成「无问题」批注"""
        paper = self._make_paper({
            "第1题": REPORT_WITH_MARKS,
            "单元7": self.NO_ISSUE_REPORT,
        })
        with open(os.path.join(paper, "单元7", "单元7.md"), "w", encoding="utf-8") as f:
            f.write("**教师版**（2022·模拟）（多选）\n如图所示，金属棒从$h$高处释放。\n")
        docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out2"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 单元原文正文已插入（粗体「教师版」被锚点拆为两个 run，分别断言）
        self.assertIn("教", doc)
        self.assertIn("师版", doc)
        self.assertIn("2022·模拟", doc)
        self.assertIn("<m:oMath>", doc)
        # 生成「无问题」批注（锚点在 Heading1 标题段内，非正文）
        self.assertEqual(cmt.count("<w:comment w:id="), 3)
        self.assertIn("无问题", cmt)
        self.assertEqual(cmt.count("无问题"), 1)
        heading_pat = re.compile(
            r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"[^>]*/>\s*</w:pPr>'
            r'\s*<w:commentRangeStart w:id="3"/>', re.DOTALL)
        self.assertIsNotNone(heading_pat.search(doc))

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
    """回归：原文字段中的 LaTeX 转义竖线 \\| 不得被当作字段分隔符。

    修复前：_PAT 按 [^|] 分割，【N|$\\left\\|…\right\\|$|改】 的 original 在
    \\| 处截断，后半截拼进 correction 还带 |，批注内容损坏。
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
        r"""\| 转义竖线整体保留在 original，批注数正确"""
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
        # 改后（单竖线公式）写入批注内容：渲染为公式图片，不再以 LaTeX 文本出现
        self.assertIn("<w:drawing>", cmt)
        self.assertNotIn(r"\left|{E}_{1}-{E}_{2}\right|", cmt)


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


REPORT_WITH_FORMULA_MARKS = """# 第1题 校对报告

轻微问题

### 标记原文
编号：第1题
内容：
【1|$v_{1}=1m/s$|$v_{1}=1\\,\\mathrm{m/s}$】

【2|$x$|$s$】

【3|$Q_{电热}$|$Q_2$】

【4|$E=BLv$|$E_1=BLv_1$】

【5|$A$|$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$】

### 修改原因
1. 公式 $E=BLv$ 符号不统一。
2. 矩阵公式 $\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$ 应降级为文本。
"""


class TestCommentFormulaImages(unittest.TestCase):
    """批注内 `$...$` 公式渲染为 PNG 图片注入。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("matplotlib 不可用，跳过公式图片测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_formula_test_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        os.makedirs(os.path.join(self.paper, "第1题"))
        with open(os.path.join(self.paper, "第1题", "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_WITH_FORMULA_MARKS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _generate(self):
        out_dir = os.path.join(self.tmp, "out")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        return z, {
            n: z.read(n).decode("utf-8")
            for n in z.namelist()
            if n in ("word/comments.xml", "word/_rels/comments.xml.rels", "[Content_Types].xml")
        }

    def test_formula_rendered_as_image(self):
        z, parts = self._generate()
        cmt = parts["word/comments.xml"]
        ET.fromstring(cmt)
        # 可渲染公式 → drawing 图片
        drawings = len(self._findall(cmt, "<w:drawing>"))
        self.assertGreaterEqual(drawings, 3)
        # 批注图片 part 写入
        media_files = [n for n in z.namelist() if "comment_pic" in n]
        self.assertEqual(len(media_files), drawings)
        # rels 注册齐全
        rels = parts["word/_rels/comments.xml.rels"]
        ET.fromstring(rels)
        self.assertEqual(len(self._findall(rels, "<Relationship ")), drawings)
        for mf in media_files:
            self.assertIn(mf.replace("word/media/", "media/"), rels)
        # png Content-Type 声明
        self.assertIn('Extension="png"', parts["[Content_Types].xml"])

    def test_unsupported_formula_degrades_to_text(self):
        _, parts = self._generate()
        cmt = parts["word/comments.xml"]
        # 矩阵公式渲染失败 → 保留原 LaTeX 文本（\\ 还原为单反斜杠、& 转义）
        self.assertIn("$\\begin{pmatrix} a &amp; b \\ c &amp; d \\end{pmatrix}$", cmt)
        # 可渲染的公式不应以 $...$ 文本残留
        self.assertNotIn("$E=BLv$", cmt)
        self.assertNotIn("$E_1=BLv_1$", cmt)
        self.assertNotIn("$v_{1}=1\\,\\mathrm{m/s}$", cmt)
        self.assertNotIn("$s$", cmt)
        self.assertNotIn("$Q_2$", cmt)

    def _findall(self, text, sub):
        return [m for m in re.finditer(re.escape(sub), text)]


class TestAnchorInsideFormula(unittest.TestCase):
    """锚点位于公式内部的标记：跳过批注、还原标记原文，防止撕裂公式。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_formula_anchor_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        q = os.path.join(self.paper, "第1题")
        os.makedirs(q)
        report = (
            "# 第1题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            "安培力做功大小为$\\frac{{B}^{2}{L}^{2}【1|$v$|$v_0$】x}{R+r}$\n\n"
            "正常标记【2|导体棒|金属棒】后续文本\n\n"
            "### 修改原因\n1. 公式内锚点。\n2. 正常标记。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_formula_anchor_skipped_and_text_restored(self):
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 公式内标记被跳过：只生成公式外那条批注
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        # 公式不转微软公式（保留为 LaTeX 文本），oMath 不包含被跳过公式
        self.assertNotIn("<m:oMath>", doc)
        # 公式以文本形式显示，并被黄色高亮（mark ==...== → w:highlight）
        self.assertIn("frac", doc)
        self.assertIn('<w:highlight w:val="yellow" />', doc)
        # 占位符已还原，无残留
        self.assertNotIn("SKIPANCH", doc)
        # 正常标记的批注仍生成
        self.assertIn("金属棒", cmt)


class TestSkipAnchorRobustness(unittest.TestCase):
    """稳健性：多个相同公式/文本时，占位符必须精确定位目标公式。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_skip_robust_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        q = os.path.join(self.paper, "第1题")
        os.makedirs(q)
        report = (
            "# 第1题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            "甲式：$\\frac{{B}^{2}{L}^{2}【1|$v$|$v_0$】x}{R+r}$\n\n"
            "乙式：$\\frac{{B}^{2}{L}^{2}vx}{R+r}$（与甲式完全相同）\n\n"
            "丙式：$\\frac{{B}^{2}{L}^{2}vx}{R+r}$\n\n"
            "### 修改原因\n1. 符号统一。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_identical_formulas_only_target_highlighted(self):
        """三个相同公式：仅含标记的甲式被文本化高亮，乙丙两式保持 oMath。"""
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 仅甲式被跳过（无批注），乙丙两式无标记不受影响
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        # 乙丙两式保持微软公式（2 个 oMath），甲式文本化不高亮误伤
        self.assertEqual(doc.count("<m:oMath>"), 2)
        self.assertIn('<w:highlight w:val="yellow" />', doc)
        # 高亮内容含甲式的 LaTeX 文本（frac），且不含 SKIPANCH 残留
        self.assertIn("frac", doc)
        self.assertNotIn("SKIPANCH", doc)

    def test_identical_text_marker_untouched(self):
        """相同文本多次出现但标记在公式外时，正常批注不受影响。"""
        q = os.path.join(self.paper, "第2题")
        os.makedirs(q)
        report = (
            "# 第2题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第2题\n内容：\n"
            "导体棒运动，导体棒【1|导体棒|金属棒】运动，导体棒停止。\n\n"
            "### 修改原因\n1. 术语统一。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out2"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 三个「导体棒」中仅第二个被锚定批注，批注内容正确
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertIn("金属棒", cmt)
        self.assertIn("导体棒", doc)
        self.assertNotIn("SKIPANCH", doc)


class TestExtremeFormulaAnchors(unittest.TestCase):
    """极端情况：标记字段内含 $、多标记同公式、空原文、公式外标记含 $。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_extreme_")
        self.paper = os.path.join(self.tmp, "测试试卷")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, qname, content):
        q = os.path.join(self.paper, qname)
        os.makedirs(q)
        report = (
            f"# {qname} 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            f"{content}\n\n### 修改原因\n1. 修正。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        return z.read("word/document.xml").decode("utf-8"), \
            z.read("word/comments.xml").decode("utf-8")

    def test_marker_field_with_dollar_inside_formula(self):
        """标记字段内含 $（【1|aaa$|bbb$】）位于公式内：识别为公式内并文本化。"""
        doc, cmt = self._make("第1题", "安培力做功大小为$\\frac{【1|aaa$|bbb$】x}{R+r}$")
        # 无批注（跳过）、公式文本化 + 高亮 + 修改意见（$ 剥离后）
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertIn('<w:highlight w:val="yellow" />', doc)
        self.assertIn("修改意见：aaa→bbb", doc)
        self.assertNotIn("SKIPANCH", doc)
        self.assertNotIn("superscript", doc)

    def test_multiple_anchors_same_formula(self):
        """同一公式内多个标记：全部还原并展示各自修改意见。"""
        doc, cmt = self._make(
            "第1题", "总功为$\\frac{【1|a|b】c【2|d|e】}{R}$")
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertIn("修改意见：a→b", doc)
        self.assertIn("修改意见：d→e", doc)
        self.assertNotIn("SKIPANCH", doc)

    def test_marker_with_dollar_outside_formula_normal_comment(self):
        """标记在公式外但字段内含 $：不误判公式内，正常生成批注。"""
        doc, cmt = self._make("第1题", "电阻【1|aaa$|bbb$】阻值，由$E=BLv$得")
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertIn("bbb", cmt)
        self.assertIn("<m:oMath>", doc)  # $E=BLv$ 正常转公式
        self.assertNotIn("修改意见", doc)

    def test_empty_orig_inside_formula(self):
        """原文为空的标记位于公式内：文本化且意见只显示改后。"""
        doc, cmt = self._make("第1题", "结果为$\\frac{【1||bbb】x}{R}$")
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertIn('<w:highlight w:val="yellow" />', doc)
        self.assertIn("修改意见：→bbb", doc)
        self.assertNotIn("SKIPANCH", doc)


class TestAnchorHeadingComments(unittest.TestCase):
    """B2：Heading1 标题锚点注入的 XML 转义与告警。"""

    @staticmethod
    def _heading_xml(w_t_text):
        return (
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            f'<w:r><w:rPr><w:b/></w:rPr><w:t>{w_t_text}</w:t></w:r></w:p>'
        )

    def test_title_with_amp_anchored(self):
        """标题含 & 时用 XML 转义后匹配 w:t 内的 &amp;。"""
        from core.docx_report import _anchor_heading_comments
        doc_xml = self._heading_xml("A&amp;B")
        result = _anchor_heading_comments(doc_xml, {1: "A&B"})
        self.assertIn('commentRangeStart w:id="1"', result)
        self.assertIn('commentReference w:id="1"', result)

    def test_title_with_lt_anchored(self):
        """标题含 < 时用 XML 转义后匹配 w:t 内的 &lt;。"""
        from core.docx_report import _anchor_heading_comments
        doc_xml = self._heading_xml("A&lt;B")
        result = _anchor_heading_comments(doc_xml, {1: "A<B"})
        self.assertIn('commentRangeStart w:id="1"', result)

    def test_unmatched_title_logs_warning(self):
        """标题匹配不到时记录告警（不再静默清掉批注）。"""
        from core import docx_report
        from core.docx_report import _anchor_heading_comments
        doc_xml = self._heading_xml("第1题")
        with mock.patch.object(docx_report, "log") as mlog:
            _anchor_heading_comments(doc_xml, {1: "不存在"})
        self.assertTrue(any("未在 Heading1 段落匹配" in c.args[0] for c in mlog.call_args_list))


if __name__ == "__main__":
    unittest.main()
