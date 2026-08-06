import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.smart_split import (
    SMART_SPLIT_PROMPT,
    parse_problem_tags,
    smart_split,
    smart_split_with_callable,
)


class TestParseProblemTags(unittest.TestCase):
    def test_single_problem(self):
        text = "<problem>第一题内容</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "第一题内容")

    def test_multiple_problems(self):
        text = "<problem>第一题</problem>中间文字<problem>第二题</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["content"], "第一题")
        self.assertEqual(result[1]["content"], "第二题")

    def test_outside_content_discarded(self):
        text = "开头引言<problem>题目内容</problem>结尾总结"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertNotIn("引言", result[0]["content"])
        self.assertNotIn("总结", result[0]["content"])

    def test_no_tags_returns_empty(self):
        text = "没有任何标记的纯文本"
        result = parse_problem_tags(text)
        self.assertEqual(result, [])

    def test_none_input_returns_empty(self):
        """LLM 返回 None 时不得崩溃（回归：re.findall 收 None 抛 TypeError）"""
        self.assertEqual(parse_problem_tags(None), [])

    def test_empty_input_returns_empty(self):
        self.assertEqual(parse_problem_tags(""), [])

    def test_multiline_problem(self):
        text = "<problem>第一行\n第二行\n第三行</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertIn("第一行", result[0]["content"])
        self.assertIn("第二行", result[0]["content"])
        self.assertIn("第三行", result[0]["content"])


class TestSmartSplitMain(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix="smart_split_t_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_successful_first_call(self):
        original = "引言\n第一题内容\n过渡\n第二题内容\n结尾"
        mock_result = (
            "引言\n<problem>第一题内容</problem>\n过渡\n<problem>第二题内容</problem>\n结尾"
        )
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            return mock_result

        result = smart_split_with_callable(original, mock_llm_call, output_root=self.tmpdir)
        self.assertEqual(len(result), 2)
        self.assertIn("第一题", result[0]["content"])
        self.assertIn("第二题", result[1]["content"])
        self.assertEqual(call_count[0], 1)

    def test_first_call_fails_second_succeeds(self):
        original = "题目内容"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                return "没有任何标记的错误返回"
            return "<problem>题目内容</problem>"

        result = smart_split_with_callable(original, mock_llm_call, output_root=self.tmpdir)
        self.assertEqual(len(result), 1)
        self.assertEqual(call_count[0], 2)

    def test_both_calls_fail_fallback_to_single(self):
        original = "全文内容作为一个单元"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            return "完全没有标记的垃圾输出"

        result = smart_split_with_callable(original, mock_llm_call, output_root=self.tmpdir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], original)
        self.assertEqual(call_count[0], 2)

    def test_empty_tags_result_fallback(self):
        original = "全文内容"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            return "<problem></problem>"

        result = smart_split_with_callable(original, mock_llm_call, output_root=self.tmpdir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], original)
        self.assertEqual(call_count[0], 2)

    def test_llm_returns_none_falls_back_to_single(self):
        """LLM 返回 None（空 content）必须降级为单单元，不得崩溃（回归）"""
        original = "题目内容全文"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            return None

        result = smart_split_with_callable(original, mock_llm_call, output_root=self.tmpdir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], original)
        self.assertEqual(call_count[0], 2)


class TestSmartSplitEdgeCases(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix="smart_split_e_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_tags_with_newlines(self):
        text = "<problem>\n题目内容\n</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "题目内容")

    def test_nested_like_pattern_not_confused(self):
        text = "<problem>正文里有 <problem> 这个词</problem>"
        result = parse_problem_tags(text)
        self.assertEqual(len(result), 1)
        self.assertIn("正文里有", result[0]["content"])

    def test_prompt_exists(self):
        self.assertIsInstance(SMART_SPLIT_PROMPT, str)
        self.assertIn("单元开始", SMART_SPLIT_PROMPT)
        self.assertIn("单元结束", SMART_SPLIT_PROMPT)
        self.assertIn("不修改原文", SMART_SPLIT_PROMPT)

    def test_smart_split_function_exists(self):
        self.assertTrue(callable(smart_split))

    def test_llm_exception_triggers_retry(self):
        original = "题目内容"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("API 超时")
            return "<problem>题目内容</problem>"

        result = smart_split_with_callable(original, mock_llm_call, output_root=self.tmpdir)
        self.assertEqual(len(result), 1)
        self.assertEqual(call_count[0], 2)

    def test_both_llm_exceptions_fallback(self):
        original = "全文"
        call_count = [0]

        def mock_llm_call(md_text, prompt):
            call_count[0] += 1
            raise RuntimeError("API 挂了")

        result = smart_split_with_callable(original, mock_llm_call, output_root=self.tmpdir)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], original)
        self.assertEqual(call_count[0], 2)

    def test_output_format_compatible_with_manual_split(self):
        text = "<problem>题目一</problem><problem>题目二</problem>"
        result = parse_problem_tags(text)
        for item in result:
            self.assertIn("content", item)
            self.assertIsInstance(item["content"], str)


class TestDumpSmartSplitRawFormat(unittest.TestCase):
    """回归：多轮 attempt 写入单文件内分节（AGENTS.md 命名约束），且不落仓库 output/。"""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix="smart_split_raw_t_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_two_attempts_single_file_with_sections(self):
        """两轮 attempt 产出单文件 _smart_split_raw.md，含两个 ### attempt 节头"""
        from shared.smart_split import smart_split_with_callable

        def mock_llm_call(md_text, prompt):
            return "没有任何标记的输出"

        smart_split_with_callable("全文", mock_llm_call,
                                  md_file="测试文档_raw.md", output_root=self.tmpdir)
        raw_path = os.path.join(self.tmpdir, "中间产物", "测试文档", "_smart_split_raw.md")
        self.assertTrue(os.path.isfile(raw_path), f"单文件应存在: {raw_path}")
        with open(raw_path, encoding="utf-8") as f:
            content = f.read()
        # 两个 attempt 节头在同一文件内
        self.assertEqual(content.count("### attempt"), 2, content)
        self.assertIn("### attempt attempt1", content)
        self.assertIn("### attempt attempt2", content)
        # 不再生成 attempt 命名的分散文件
        files = os.listdir(os.path.join(self.tmpdir, "中间产物", "测试文档"))
        self.assertFalse(any("attempt" in f for f in files), files)

    def test_no_repo_output_pollution(self):
        """output_root 指定后仓库 output/ 目录不得被写入"""
        from shared.smart_split import smart_split_with_callable

        def mock_llm_call(md_text, prompt):
            return "没有任何标记的输出"

        repo_output = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
        target_dir = os.path.join(repo_output, "中间产物", "未命名文档")
        # 清理可能存在的旧残留，确保本次运行前干净
        import shutil
        shutil.rmtree(target_dir, ignore_errors=True)

        smart_split_with_callable("全文", mock_llm_call, output_root=self.tmpdir)
        # 本次运行不得在仓库 output/ 下产生任何文件
        self.assertFalse(os.path.exists(target_dir),
                         f"仓库 output/ 被测试污染: {os.listdir(target_dir) if os.path.exists(target_dir) else ''}")

    def test_smart_split_wrapper_passes_output_root(self):
        """回归：生产包装函数 smart_split() 必须透传 output_root（真实调用链走此函数）"""
        from unittest import mock
        from shared import smart_split as ss

        repo_output = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
        target_dir = os.path.join(repo_output, "中间产物", "未命名文档")
        import shutil
        shutil.rmtree(target_dir, ignore_errors=True)

        fake_api_result = {"content": "没有任何标记的输出"}
        with mock.patch.object(ss, "call_api", return_value=fake_api_result):
            problems = ss.smart_split("全文内容", "http://x", "k", "m",
                                      md_file="测试文档_raw.md",
                                      output_root=self.tmpdir)
        # 降级为单单元
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["content"], "全文内容")
        # 中间产物落盘到 output_root（包装函数透传生效）
        raw_path = os.path.join(self.tmpdir, "中间产物", "测试文档", "_smart_split_raw.md")
        self.assertTrue(os.path.isfile(raw_path),
                        f"包装函数未透传 output_root，中间产物未落到指定目录: {raw_path}")
        # 仓库 output/ 不得新增残留
        self.assertFalse(os.path.exists(target_dir),
                         f"仓库 output/ 被污染: {target_dir}")


if __name__ == "__main__":
    unittest.main()
