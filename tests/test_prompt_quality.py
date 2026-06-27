import unittest
import sys
import os
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_subject():
    subject_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
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
        md = '内容<批注 id=1><原>此处</原><改>批注</改></批注>'
        prompt = build_review_prompt(md)
        self.assertIn("正确", prompt)
        self.assertIn("有误", prompt)
        self.assertIn("部分正确", prompt)

    def test_prompt_contains_supplement_instruction(self):
        from shared.review_mode import build_review_prompt
        md = '内容<批注 id=1><原>此处</原><改>批注</改></批注>'
        prompt = build_review_prompt(md)
        self.assertIn("补充", prompt)
        self.assertIn("遗漏", prompt)

    def test_prompt_contains_output_format(self):
        from shared.review_mode import build_review_prompt
        md = '内容<批注 id=1><原>此处</原><改>批注</改></批注>'
        prompt = build_review_prompt(md)
        self.assertIn("输出格式", prompt)

    def test_prompt_lists_all_comments(self):
        from shared.review_mode import build_review_prompt
        md = 'a<批注 id=1><原>此处</原><改>批注一</改></批注>b<批注 id=2><原>此处</原><改>批注二</改></批注>c'
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
        # 新指令结构：
        # 1. 核心定位：自身知识为主，不含"情况A/B"
        # 2. 直接URL源列表：识典古籍、搜韵网、中国作家网、百度直达
        # 3. 使用规则 + 严禁搜索
        idx_core = instructions.find("自身知识直接校对")
        idx_shidian = instructions.find("识典古籍")
        idx_souyun = instructions.find("搜韵网")
        idx_chinawriter = instructions.find("中国作家网")
        idx_baidu = instructions.find("百度直达")
        idx_forbidden = instructions.find("严禁搜索")
        idx_web_fetch = instructions.find("web_fetch")
        self.assertGreater(idx_core, 0, "应强调基于自身知识校对")
        self.assertGreater(idx_shidian, 0, "应包含识典古籍")
        self.assertGreater(idx_souyun, 0, "应包含搜韵网")
        self.assertGreater(idx_chinawriter, 0, "应包含中国作家网")
        self.assertGreater(idx_baidu, 0, "应包含百度直达")
        self.assertGreater(idx_forbidden, 0, "应包含严禁搜索的情形")
        self.assertGreater(idx_web_fetch, 0, "应包含 web_fetch 工具")


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


class TestConditionalClassicValidation(unittest.TestCase):
    """config 的古诗文验证指令必须条件化:已提供前置参考则不搜,未提供则必搜。

    回归用例:config 第9行原为无条件硬指令"必须通过工具检索",与前置参考块
    "无需再搜"的软建议冲突,LLM 服从更硬的 config 指令,导致前置搜成功了仍反复搜网页。
    """

    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)

    def test_question_prompt_has_conditional_validation(self):
        prompt = self.app.get_question_prompt()
        # 已提供前置参考 → 不搜
        self.assertIn("前置参考", prompt)
        self.assertIn("不得再检索", prompt)
        # 未提供前置参考 → 必搜(兜底不削弱验证能力)
        self.assertIn("未提供前置参考", prompt)

    def test_tool_instructions_has_hard_no_search_rule(self):
        instructions = self.app.get_tool_instructions()
        # 软建议"无需"应升级为硬约束"严禁"
        self.assertIn("严禁", instructions)
        self.assertIn("web_search", instructions)


class TestMaxToolLoops(unittest.TestCase):
    """工具轮次上限应给足余地,避免搜原文多轮场景被强制无工具收尾。"""

    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)

    def test_max_tool_loops_sufficient(self):
        # 新指令极度限制搜索，3 轮足以覆盖极端情况
        self.assertGreaterEqual(self.app.get_max_tool_loops(), 3)


if __name__ == "__main__":
    unittest.main()
