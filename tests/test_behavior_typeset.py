"""行为测试：排版模式的真实用户场景（真实 pandoc / xelatex 执行）。

覆盖两个已修复的行为缺陷，从用户操作出发断言真实落盘产物：
1. 仅排版模式取消「生成 LaTeX PDF 校对报告」→ 不得执行 LaTeX 排版
   （修复前 start_generate_pdf 无条件生成 PDF，不尊重勾选状态）
2. 输出目录为相对路径 → docx 必须真实落在相对 CWD 的目录且结构健全
   （修复前 pandoc 以临时目录为 cwd，docx 被写进临时目录，批注注入打开失败）

与单元测试（tests/test_default_app_typeset.py、tests/test_docx_report.py）的区别：
不 mock generate_combined_pdf / generate_combined_docx，走完整生成链路
（pandoc/xelatex 真实编译），断言目录、文件与 XML 结构。
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from ui import default_app
except Exception:
    default_app = None

from core.pandoc_utils import find_pandoc

_1PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

REPORT_1 = """# 第1题 校对报告

轻微问题

### 标记原文
编号：第1题
内容：
1．下列关于物理量的说法正确的是（　　）

【1|电荷量很小的电荷就是元电荷|元电荷是最小的电荷量，并非电荷量很小的电荷】

【2|电量|电荷量】是电荷的多少

![@@@testuuid00000000000000000000000001](./images/图1.png){width="1.0in" height="0.8in"}

### 修改原因
1. 元电荷是最小的电荷量，表述不严谨。
2. "电量"为口语化表述，应规范为"电荷量"。
"""

REPORT_2 = """无问题

---

## 📋 工具调用日志

共调用 1 次

## 📋 模型思考过程（仅核查用，不出现在 PDF 中）

题目与解答均无错误。
"""

ORIG_1 = "1．下列关于物理量的说法正确的是（　　）"
ORIG_2 = "2．下列说法正确的是（　　）"

DATA_1 = {
    "summary": "轻微问题",
    "marked_text": "### 标记原文\n编号：第1题\n内容：\n1．下列关于物理量的说法正确的是（　　）\n\n"
                   "【1|电荷量很小的电荷就是元电荷|元电荷是最小的电荷量，并非电荷量很小的电荷】\n\n"
                   "【2|电量|电荷量】是电荷的多少\n",
    "corrections": [
        {"original": "电荷量很小的电荷就是元电荷",
         "correction": "元电荷是最小的电荷量，并非电荷量很小的电荷",
         "type": "概念"},
        {"original": "电量", "correction": "电荷量", "type": "术语"},
    ],
}

DATA_2 = {
    "summary": "无问题",
    "marked_text": "2．下列说法正确的是（　　）",
    "corrections": [],
}


class FakeVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class FakePipeline:
    typeset_enabled = True


class FakeBtn:
    def __init__(self):
        self.calls = []

    def config(self, **kw):
        self.calls.append(kw)


class FakeRoot:
    def after(self, *args):
        pass


class _SyncThread:
    """把 threading.Thread 换成同步执行（仅改变执行方式，不改变行为）。"""

    def __init__(self, target, *args, **kw):
        self._target = target

    def start(self):
        self._target()


@unittest.skipIf(default_app is None, "tkinter 不可用")
class TestTypesetOnlyModeBehavior(unittest.TestCase):
    """真实用户场景：勾选状态 → start_generate_pdf → 断言落盘产物。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用")

    def setUp(self):
        self._old_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix="_behavior_typeset_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        self.out_root = os.path.join(self.tmp, "输出")

        for q, report, orig, data in (
            ("第1题", REPORT_1, ORIG_1, DATA_1),
            ("第2题", REPORT_2, ORIG_2, DATA_2),
        ):
            q_dir = os.path.join(self.paper, q)
            os.makedirs(q_dir)
            with open(os.path.join(q_dir, "_校对报告.md"), "w", encoding="utf-8") as f:
                f.write(report)
            with open(os.path.join(q_dir, f"{q}.md"), "w", encoding="utf-8") as f:
                f.write(orig)
            with open(os.path.join(q_dir, "_校对数据.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        os.makedirs(os.path.join(self.paper, "第1题", "images"))
        with open(os.path.join(self.paper, "第1题", "images", "图1.png"), "wb") as f:
            f.write(_1PX_PNG)

        self._thread_patch = mock.patch.object(default_app.threading, "Thread", _SyncThread)
        self._thread_patch.start()

    def tearDown(self):
        self._thread_patch.stop()
        os.chdir(self._old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_app(self, pdf, docx, output_dir=None):
        app = object.__new__(default_app.DefaultApp)
        app.proofread_list = [(self.paper, "测试试卷")]
        app.task_running = False
        app.task_interrupt = False
        app.proofread_result = {}
        app.output_dir = FakeVar(output_dir or self.out_root)
        app.generate_pdf = FakeVar(pdf)
        app.generate_docx = FakeVar(docx)
        app.pipeline = FakePipeline()
        app.btn_action = FakeBtn()
        app.btn_stop = FakeBtn()
        app.root = FakeRoot()
        return app

    def test_uncheck_pdf_generates_word_only(self):
        """用户行为：仅排版模式，取消 LaTeX PDF、只勾 Word → 只出 Word。

        修复前：PDF 无条件生成（校对PDF 目录会被创建）；修复后不得出现。
        """
        app = self._make_app(pdf=False, docx=True)
        app.start_generate_pdf()

        pdf_dir = os.path.join(self.out_root, "校对PDF")
        self.assertFalse(os.path.exists(pdf_dir), "取消勾选后仍执行了 LaTeX 排版")

        docx_path = os.path.join(self.out_root, "校对Word", "测试试卷_校对批注版.docx")
        self.assertTrue(os.path.exists(docx_path), f"Word 报告未生成：{docx_path}")
        self._assert_docx_sound(docx_path, n_comments=3)

    @unittest.skipIf(shutil.which("xelatex") is None, "xelatex 不可用")
    def test_uncheck_word_generates_pdf_only(self):
        """对称行为：取消 Word、只勾 LaTeX PDF → 只出 PDF。"""
        app = self._make_app(pdf=True, docx=False)
        app.start_generate_pdf()

        pdf_path = os.path.join(self.out_root, "校对PDF", "测试试卷.pdf")
        self.assertTrue(os.path.exists(pdf_path), f"PDF 未生成：{pdf_path}")
        with open(pdf_path, "rb") as f:
            self.assertTrue(f.read(4).startswith(b"%PDF"), "产物不是合法 PDF")

        word_dir = os.path.join(self.out_root, "校对Word")
        self.assertFalse(os.path.exists(word_dir), "取消勾选后仍生成了 Word 报告")

    def test_relative_output_dir_real_artifacts(self):
        """用户行为：输出目录填相对路径 → docx 真实落在相对 CWD 的目录且结构健全。

        修复前：pandoc 以临时目录为 cwd，docx 被写进临时目录（随即删除），
        批注注入打开相对路径抛 FileNotFoundError，最终无任何产物。
        """
        os.chdir(self.tmp)
        app = self._make_app(pdf=False, docx=True, output_dir="输出")
        app.start_generate_pdf()

        rel_docx = os.path.join("输出", "校对Word", "测试试卷_校对批注版.docx")
        self.assertTrue(os.path.exists(rel_docx), f"docx 未落在 CWD 相对目录：{rel_docx}")
        self._assert_docx_sound(rel_docx, n_comments=3)

    def _assert_docx_sound(self, path, n_comments):
        """校验 docx 结构健全（批注计数一致、XML 可解析，Word 可打开的前提）。"""
        z = zipfile.ZipFile(path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        ET.fromstring(doc)
        ET.fromstring(cmt)
        n_start = doc.count("<w:commentRangeStart")
        n_end = doc.count("<w:commentRangeEnd")
        n_ref = doc.count("<w:commentReference")
        self.assertEqual(cmt.count("<w:comment w:id="), n_comments)
        self.assertEqual(n_start, n_end)
        self.assertEqual(n_end, n_ref)
        self.assertEqual(n_ref, n_comments)


if __name__ == "__main__":
    unittest.main()
