"""回归：start_generate_pdf（仅排版入口）必须受「生成 LaTeX PDF 校对报告」勾选控制。

修复前：PDF 生成无条件执行，用户取消勾选后仍生成 LaTeX PDF；
完整流程入口 start_full_pipeline 有 generate_pdf.get() 检查，两入口行为不一致。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from ui import default_app
except Exception:
    default_app = None


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
    """把 threading.Thread 换成同步执行，避免与 daemon 线程竞态。"""

    def __init__(self, target, *args, **kw):
        self._target = target

    def start(self):
        self._target()


def _make_app(generate_pdf, generate_docx):
    app = object.__new__(default_app.DefaultApp)
    app.proofread_list = [("/假/目录", "测试试卷")]
    app.task_running = False
    app.task_interrupt = False
    app.proofread_result = {}
    app.output_dir = FakeVar("/假/输出")
    app.generate_pdf = FakeVar(generate_pdf)
    app.generate_docx = FakeVar(generate_docx)
    app.pipeline = FakePipeline()
    app.btn_action = FakeBtn()
    app.btn_stop = FakeBtn()
    app.root = FakeRoot()
    return app


@unittest.skipIf(default_app is None, "tkinter 不可用")
class TestStartGeneratePdfRespectsCheckboxes(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.object(default_app, "generate_combined_pdf", return_value="/out/1.pdf"),
            mock.patch.object(default_app, "generate_combined_docx", return_value="/out/1.docx"),
            mock.patch.object(default_app.threading, "Thread", _SyncThread),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_pdf_unchecked_only_docx(self):
        """回归：取消「生成 LaTeX PDF 校对报告」后不得生成 PDF，只生成 Word"""
        app = _make_app(generate_pdf=False, generate_docx=True)
        app.start_generate_pdf()
        default_app.generate_combined_pdf.assert_not_called()
        default_app.generate_combined_docx.assert_called_once()

    def test_docx_unchecked_only_pdf(self):
        """对称：取消 Word 勾选后只生成 PDF"""
        app = _make_app(generate_pdf=True, generate_docx=False)
        app.start_generate_pdf()
        default_app.generate_combined_pdf.assert_called_once()
        default_app.generate_combined_docx.assert_not_called()

    def test_both_checked(self):
        """两者都勾选时都生成"""
        app = _make_app(generate_pdf=True, generate_docx=True)
        app.start_generate_pdf()
        default_app.generate_combined_pdf.assert_called_once()
        default_app.generate_combined_docx.assert_called_once()


if __name__ == "__main__":
    unittest.main()
