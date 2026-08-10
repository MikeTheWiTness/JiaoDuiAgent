'''测试 read_md_for_unit 文件选择逻辑（ADR 0004 决策 4）

验证：当目录中有多个 .md 文件时，read_md_for_unit 精确读取与目录同名的 .md。
本文件导入 core.defaults.read_md_for_unit 真实实现进行断言。
'''
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.defaults import read_md_for_unit


class TestProofreadOneFileSelection(unittest.TestCase):
    '''验证 read_md_for_unit 精确匹配目录名的行为'''

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

    # ---- 旧逻辑（仅用于 bug 文档，不复用） ----

    @staticmethod
    def _read_md_old(q_dir):
        '''旧逻辑：遍历目录取第一个 .md（有 bug）

        显式 sorted 保证确定性：下划线（ASCII 0x5F）排在中文前，
        避免 os.listdir 枚举顺序随文件系统（ext4/APFS/NTFS）漂移。
        '''
        for f in sorted(os.listdir(q_dir)):
            if f.endswith(".md"):
                with open(os.path.join(q_dir, f), encoding='utf-8') as fm:
                    return fm.read()
        return None

    # ---- 测试 ----

    def test_old_code_reads_wrong_file_when_underscore_name_first(self):
        '''暴露旧代码 bug：下划线开头的 .md 文件在排序中排在前面'''
        d = self._qdir("第1题")
        self._write(d, "_第1题_clean.md", "干净正文")
        self._write(d, "第1题.md", "含标记的正文")

        old = self._read_md_old(d)
        # 旧代码读到 _clean.md（bug！）
        self.assertEqual(old, "干净正文",
                         "旧代码应读到 _ 开头的 _clean.md — 这就是要修复的 bug")

    def test_reads_correct_md_when_underscore_name_first(self):
        '''新代码（read_md_for_unit）在有 _clean 干扰时仍读取正确的 md'''
        d = self._qdir("第1题")
        self._write(d, "_第1题_clean.md", "干净正文")
        self._write(d, "第1题.md", "含标记的正文")

        result = read_md_for_unit(d, "第1题")
        self.assertEqual(result, "含标记的正文",
                         "read_md_for_unit 精确匹配，应读到与目录同名的 md")

    def test_reads_correct_md_when_3_md_files_exist(self):
        '''3 个 .md 共存时读到正确的'''
        d = self._qdir("第1题")
        self._write(d, "第1题.md", "含标记的正文")
        self._write(d, "_校对报告.md", "校对结果")
        self._write(d, "_第1题_clean.md", "干净正文")

        result = read_md_for_unit(d, "第1题")
        self.assertEqual(result, "含标记的正文")

    def test_single_md_still_works(self):
        '''只有一个 .md 时新旧逻辑都能读到'''
        d = self._qdir("第1题")
        self._write(d, "第1题.md", "唯一正文")

        self.assertEqual(self._read_md_old(d), "唯一正文")
        self.assertEqual(read_md_for_unit(d, "第1题"), "唯一正文")

    def test_no_matching_md_returns_none(self):
        '''没有同名 .md 时返回 None'''
        d = self._qdir("第1题")
        self._write(d, "其他文件.md", "不是目标")

        result = read_md_for_unit(d, "第1题")
        self.assertIsNone(result)

    def test_special_chars_in_q_name(self):
        '''q_name 含括号、空格等特殊字符'''
        name = "板块1(文言文)-基础"
        d = self._qdir(name)
        self._write(d, f"{name}.md", "板块正文")

        result = read_md_for_unit(d, name)
        self.assertEqual(result, "板块正文")

    def test_only_matches_md_not_txt(self):
        '''只匹配 .md 扩展名'''
        d = self._qdir("第1题")
        self._write(d, "第1题.txt", "文本")
        self._write(d, "第1题.md", "markdown")

        result = read_md_for_unit(d, "第1题")
        self.assertEqual(result, "markdown")


if __name__ == "__main__":
    unittest.main()


class TestProofreadPersistenceDecoupled(unittest.TestCase):
    """单题报告落盘与 generate_pdf 勾选解耦——generate_pdf=False 时仍落盘。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="tdd_persist_")
        self.q_dir = os.path.join(self.tmpdir, "第1题")
        os.makedirs(self.q_dir, exist_ok=True)
        with open(os.path.join(self.q_dir, "第1题.md"), "w", encoding="utf-8") as f:
            f.write("1．题目\n\n【1|错误|正确】\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_proofread(self, generate_pdf, content=None, reasoning="思考"):
        from unittest import mock

        from core import defaults
        from core.api_client import StopReason
        from core.session_context import SessionContext

        ctx = SessionContext(api_url="http://x", api_key="k", model="m",
                             max_loops=1, output_dir=self.tmpdir)
        if content is None:
            content = "轻微问题\n\n### 标记原文\n编号：第1题\n内容：\n1．题目【1|错误|正确】\n\n### 修改原因\n1. 修正错误。"
        fake_result = {
            "content": content,
            "tool_calls_log": [],
            "reasoning": reasoning,
            "usage": {"total_tokens": 100},
            "stop_reason": StopReason.END_TURN,
        }
        with mock.patch.object(defaults, "call_api", return_value=fake_result), \
                mock.patch.object(defaults, "_enforce_format", return_value=(True, [])):
            return defaults.default_proofread_one(
                ctx, self.q_dir, "第1题", "prompt", [], generate_pdf=generate_pdf,
                archive_root=self.tmpdir)

    def test_no_issue_report_excludes_reasoning(self):
        """回归：思考内容不得写入 _校对报告.md（含存档副本）

        修复前：「无问题」时 reasoning 被追加为「模型思考过程」段；
        修复后：思考内容归属 _API对话记录.md，报告只保留校对相关内容。
        """
        r = self._run_proofread(generate_pdf=False, content="无问题",
                                reasoning="这是模型思考内容XYZ")
        self.assertTrue(r["success"])
        archive = os.path.join(self.tmpdir, "中间产物",
                               os.path.basename(self.tmpdir.rstrip("/\\")), "第1题")
        for rep in (os.path.join(self.q_dir, "_校对报告.md"),
                    os.path.join(archive, "_校对报告.md")):
            self.assertTrue(os.path.exists(rep), f"缺少 {rep}")
            text = open(rep, encoding="utf-8").read()
            self.assertNotIn("模型思考过程", text)
            self.assertNotIn("这是模型思考内容XYZ", text)
            self.assertIn("完整 API 对话记录请见", text)

    def test_report_persists_when_generate_pdf_false(self):
        r = self._run_proofread(generate_pdf=False)
        self.assertTrue(r["success"])
        self.assertTrue(os.path.exists(os.path.join(self.q_dir, "_校对报告.md")))
        self.assertTrue(os.path.exists(os.path.join(self.q_dir, "_校对数据.json")))

    def test_report_persists_when_generate_pdf_true(self):
        r = self._run_proofread(generate_pdf=True)
        self.assertTrue(r["success"])
        self.assertTrue(os.path.exists(os.path.join(self.q_dir, "_校对报告.md")))
        self.assertTrue(os.path.exists(os.path.join(self.q_dir, "_校对数据.json")))


class TestInterruptedProofread(unittest.TestCase):
    """回归：工具循环中断（INTERRUPTED）不能被当作成功处理。

    修复前：stop_reason=INTERRUPTED 走成功分支，空内容落盘并返回 success=True；
    修复后：与 ERROR 同级，不落盘、不做格式修正，返回 success=False。
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="tdd_interrupt_")
        self.q_dir = os.path.join(self.tmpdir, "第1题")
        os.makedirs(self.q_dir, exist_ok=True)
        with open(os.path.join(self.q_dir, "第1题.md"), "w", encoding="utf-8") as f:
            f.write("1．题目\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_with_stop_reason(self, stop_reason, content=""):
        from unittest import mock

        from core import defaults
        from core.session_context import SessionContext

        ctx = SessionContext(api_url="http://x", api_key="k", model="m",
                             max_loops=1, output_dir=self.tmpdir)
        fake_result = {
            "content": content,
            "tool_calls_log": [],
            "reasoning": "",
            "usage": {"total_tokens": 0},
            "stop_reason": stop_reason,
        }
        with mock.patch.object(defaults, "call_api", return_value=fake_result), \
                mock.patch.object(defaults, "_enforce_format",
                                  side_effect=AssertionError("中断后不应做格式修正")):
            return defaults.default_proofread_one(
                ctx, self.q_dir, "第1题", "prompt", [], generate_pdf=True)

    def test_interrupted_returns_failure(self):
        """中断必须返回 success=False"""
        from core.api_client import StopReason
        r = self._run_with_stop_reason(StopReason.INTERRUPTED)
        self.assertFalse(r["success"])
        self.assertTrue(r["error"])

    def test_interrupted_does_not_persist_report(self):
        """中断后不得落盘 _校对报告.md / _校对数据.json"""
        from core.api_client import StopReason
        self._run_with_stop_reason(StopReason.INTERRUPTED)
        self.assertFalse(os.path.exists(os.path.join(self.q_dir, "_校对报告.md")))
        self.assertFalse(os.path.exists(os.path.join(self.q_dir, "_校对数据.json")))

    def test_error_also_returns_failure(self):
        """ERROR 保持原有失败语义（对照组）"""
        from core.api_client import StopReason
        r = self._run_with_stop_reason(StopReason.ERROR, content="错误详情")
        self.assertFalse(r["success"])

    def test_end_turn_still_succeeds(self):
        """正常结束（END_TURN）仍走成功分支（对照组）"""
        from unittest import mock

        from core import defaults
        from core.api_client import StopReason
        from core.session_context import SessionContext

        ctx = SessionContext(api_url="http://x", api_key="k", model="m",
                             max_loops=1, output_dir=self.tmpdir)
        fake_result = {
            "content": "无问题",
            "tool_calls_log": [],
            "reasoning": "",
            "usage": {"total_tokens": 0},
            "stop_reason": StopReason.END_TURN,
        }
        with mock.patch.object(defaults, "call_api", return_value=fake_result), \
                mock.patch.object(defaults, "_enforce_format", return_value=(True, [])):
            r = defaults.default_proofread_one(
                ctx, self.q_dir, "第1题", "prompt", [], generate_pdf=False,
                archive_root=self.tmpdir)
        self.assertTrue(r["success"])
        self.assertTrue(os.path.exists(os.path.join(self.q_dir, "_校对报告.md")))


class TestStripSearchFromPrompt(unittest.TestCase):
    """回归：_strip_search_from_prompt 必须剥离搜索工具段。

    修复前：lookahead (?=\n## ) 要求搜索段后有其他 ## 标题，真实提示词把
    搜索段放末尾 → 剥离永不生效；语文的段标题也不同。
    """

    def test_search_section_at_end_stripped(self):
        """搜索段在提示词末尾（真实结构）必须被剥离"""
        from core.defaults import _strip_search_from_prompt
        prompt = ("## 基本校对规则\n必须仔细校对。\n\n"
                  "## 可用的联网搜索工具\n先调 web_search 搜索，再作答。\n- 工具说明")
        cleaned = _strip_search_from_prompt(prompt)
        self.assertNotIn("web_search", cleaned)
        self.assertNotIn("可用的联网搜索工具", cleaned)
        self.assertIn("基本校对规则", cleaned)

    def test_search_section_in_middle_stripped(self):
        """搜索段在中间时剥离到下一个 ## 标题"""
        from core.defaults import _strip_search_from_prompt
        prompt = ("## 开头\n内容A\n\n## 可用的联网搜索工具\n搜索说明\n\n"
                  "## 后续标题\n内容B")
        cleaned = _strip_search_from_prompt(prompt)
        self.assertNotIn("搜索说明", cleaned)
        self.assertIn("后续标题", cleaned)
        self.assertIn("内容B", cleaned)

    def test_chinese_classics_heading_stripped(self):
        """高中语文的「## 原文检索（仅供极端情况使用）」标题也必须剥离"""
        from core.defaults import _strip_search_from_prompt
        prompt = ("## 校对要求\n内容\n\n"
                  "## 原文检索（仅供极端情况使用）\n用 web_fetch 直达网站")
        cleaned = _strip_search_from_prompt(prompt)
        self.assertNotIn("web_fetch", cleaned)
        self.assertIn("校对要求", cleaned)

    def test_no_search_section_unchanged(self):
        """无搜索段时提示词原样保留"""
        from core.defaults import _strip_search_from_prompt
        prompt = "## 只有一段\n没有搜索工具"
        self.assertEqual(_strip_search_from_prompt(prompt), prompt)

    def test_empty_prompt(self):
        from core.defaults import _strip_search_from_prompt
        self.assertEqual(_strip_search_from_prompt(""), "")
