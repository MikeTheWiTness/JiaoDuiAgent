import unittest
import sys
import os
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load_subject():
    subject_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "subjects", "高中语文v1.1"
    )
    spec = importlib.util.spec_from_file_location(
        "yuwen_subject",
        os.path.join(subject_dir, "subject.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SubjectApp, subject_dir


SubjectApp, SUBJECT_DIR = _load_subject()


class TestQuestionPromptQuality(unittest.TestCase):
    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)

    def test_prompt_contains_answer_check_instruction(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("答案", prompt)
        self.assertTrue(
            "有答案" in prompt or "参考答案" in prompt,
            "提示词应包含'有答案校答案'相关说明"
        )

    def test_prompt_clear_answer_first_principle(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("有答案先校答案", prompt)
        self.assertIn("无答案校题干", prompt)

    def test_prompt_contains_classic_text_validation(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("古诗文", prompt)
        self.assertIn("权威", prompt)

    def test_prompt_contains_tool_usage_instructions(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("web_fetch", prompt)
        self.assertIn("web_search", prompt)

    def test_prompt_mentions_shidianguji(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("识典古籍", prompt)

    def test_prompt_mentions_souyun(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("搜韵", prompt)

    def test_prompt_has_mark_format(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("【", prompt)
        self.assertIn("】", prompt)
        self.assertIn("|", prompt)

    def test_prompt_mentions_summary_levels(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("无问题", prompt)
        self.assertIn("严重", prompt)


class TestSmartSplitPrompt(unittest.TestCase):
    def test_prompt_contains_problem_tags(self):
        from shared.smart_split import SMART_SPLIT_PROMPT
        self.assertIn("<problem>", SMART_SPLIT_PROMPT)
        self.assertIn("</problem>", SMART_SPLIT_PROMPT)

    def test_prompt_says_no_modification(self):
        from shared.smart_split import SMART_SPLIT_PROMPT
        self.assertTrue(
            "不修改" in SMART_SPLIT_PROMPT or "不改" in SMART_SPLIT_PROMPT,
            "智能分割提示词应强调不修改原文"
        )

    def test_prompt_contains_example(self):
        from shared.smart_split import SMART_SPLIT_PROMPT
        self.assertIn("示例", SMART_SPLIT_PROMPT)


class TestReviewPrompt(unittest.TestCase):
    def test_prompt_contains_three_verdicts(self):
        from shared.review_mode import build_review_prompt
        md = "内容[📝批注1：批注]"
        prompt = build_review_prompt(md)
        self.assertIn("正确", prompt)
        self.assertIn("有误", prompt)
        self.assertIn("部分正确", prompt)

    def test_prompt_contains_supplement_instruction(self):
        from shared.review_mode import build_review_prompt
        md = "内容[📝批注1：批注]"
        prompt = build_review_prompt(md)
        self.assertIn("补充", prompt)
        self.assertIn("遗漏", prompt)

    def test_prompt_contains_output_format(self):
        from shared.review_mode import build_review_prompt
        md = "内容[📝批注1：批注]"
        prompt = build_review_prompt(md)
        self.assertIn("输出格式", prompt)

    def test_prompt_lists_all_comments(self):
        from shared.review_mode import build_review_prompt
        md = "a[📝批注1：批注一]b[📝批注2：批注二]c"
        prompt = build_review_prompt(md)
        self.assertIn("批注1", prompt)
        self.assertIn("批注一", prompt)
        self.assertIn("批注2", prompt)
        self.assertIn("批注二", prompt)


class TestReferenceSection(unittest.TestCase):
    def test_reference_section_clear_structure(self):
        from shared.chinese_classics_tools import build_reference_section
        diffs = [{"original": "明", "given": "名", "position": 2, "type": "replace"}]
        result = build_reference_section("poetry", "床前明月光", diffs)
        self.assertIn("权威原文", result)
        self.assertIn("差异", result)
        self.assertIn("自动比对", result)

    def test_reference_section_warning_note(self):
        from shared.chinese_classics_tools import build_reference_section
        diffs = [{"original": "明", "given": "名", "position": 2, "type": "replace"}]
        result = build_reference_section("poetry", "床前明月光", diffs)
        self.assertTrue(
            "结合语境" in result or "自动比对" in result,
            "应提示差异为自动比对结果，需结合语境判断"
        )

    def test_no_diff_confirmation(self):
        from shared.chinese_classics_tools import build_reference_section
        result = build_reference_section("poetry", "床前明月光", [])
        self.assertTrue(
            "一致" in result or "无差异" in result,
            "无差异时应明确告知一致"
        )


class TestToolInstructions(unittest.TestCase):
    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)

    def test_tools_include_fetch_and_search(self):
        instructions = self.app.get_tool_instructions()
        self.assertIn("web_fetch", instructions)
        self.assertIn("web_search", instructions)

    def test_instructions_mentions_shidianguji_scenario(self):
        instructions = self.app.get_tool_instructions()
        self.assertIn("识典古籍", instructions)
        self.assertIn("文言文", instructions)

    def test_instructions_mentions_souyun_scenario(self):
        instructions = self.app.get_tool_instructions()
        self.assertIn("搜韵", instructions)
        self.assertIn("诗", instructions)

    def test_instructions_priority_order(self):
        instructions = self.app.get_tool_instructions()
        idx_shidain_rule = instructions.find("优先使用 web_fetch 访问识典古籍")
        idx_then_search = instructions.find("再用 web_search")
        self.assertGreater(idx_shidain_rule, 0, "应包含'优先使用识典古籍'的规则")
        self.assertGreater(idx_then_search, 0, "应包含'再用web_search'的规则")
        self.assertLess(idx_shidain_rule, idx_then_search,
                        "优先规则应在'再用web_search'之前，体现优先级")


class TestPreProofreadHook(unittest.TestCase):
    def test_hook_returns_string(self):
        app = SubjectApp(SUBJECT_DIR)
        result = app.pre_proofread_hook("普通文本")
        self.assertIsInstance(result, str)

    def test_modern_text_unchanged_basically(self):
        app = SubjectApp(SUBJECT_DIR)
        text = "这是现代文阅读题，关于科学发展的文章。"
        result = app.pre_proofread_hook(text)
        self.assertIn("这是现代文", result)


if __name__ == "__main__":
    unittest.main()
