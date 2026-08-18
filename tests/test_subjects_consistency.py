"""7 个学科 SubjectApp 一致性护栏（除高中语文外其余 6 科此前零覆盖）。

验证：
- 接口方法齐全且与 BaseSubjectApp 签名兼容（防学科间接口漂移）
- 非 ReAct 模式下有工具的学科，question prompt 必须包含工具指令
  （回归：高中化学非 ReAct 分支漏拼 get_tool_instructions，工具静默失效）
- 每个学科真实 config.json 通过 validate_config
- 小学数学 main.py 的 subject_dir 在开发模式下解析到学科目录
"""
import importlib.util
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBJECTS_ROOT = os.path.join(REPO_ROOT, "subjects")

SUBJECT_DIRS = sorted(
    d for d in os.listdir(SUBJECTS_ROOT)
    if os.path.isdir(os.path.join(SUBJECTS_ROOT, d))
)

REQUIRED_METHODS = [
    "build_tools",
    "get_max_tool_loops",
    "get_tool_instructions",
    "get_question_prompt",
    "get_review_prompt",
    "split_lecture",
    "split_exam",
    "generate_knowledge",
    "collect_paper_dirs",
    "proofread_one",
    "pre_proofread_hook",
    "post_proofread_hook",
]


def _load_subject(subject_dir):
    spec = importlib.util.spec_from_file_location(
        f"subject_{subject_dir}", os.path.join(subject_dir, "subject.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSubjectsInterfaceConsistency(unittest.TestCase):
    """每个学科都实例化并验证接口齐全"""

    def test_all_seven_subjects_exist(self):
        self.assertEqual(
            sorted(SUBJECT_DIRS),
            ["初中英语v3.0", "小学数学v3.0", "小学语文v3.0",
             "高中化学v3.0", "高中历史v3.0", "高中物理v3.0", "高中语文v3.0"])

    def test_required_methods_present_in_all_subjects(self):
        for d in SUBJECT_DIRS:
            subject_dir = os.path.join(SUBJECTS_ROOT, d)
            mod = _load_subject(subject_dir)
            app = mod.SubjectApp(subject_dir)
            for m in REQUIRED_METHODS:
                self.assertTrue(hasattr(app, m) and callable(getattr(app, m)),
                                f"{d} 缺少接口方法 {m}")
                self.assertIsInstance(inspect.signature(getattr(app, m)),
                                      inspect.Signature,
                                      f"{d}.{m} 签名异常")

    def test_base_stub_methods_overridden(self):
        """基类抛 NotImplementedError 的接口必须被子类真实实现覆盖"""
        from core.base_subject import BaseSubjectApp
        stubs = {m for m, f in vars(BaseSubjectApp).items()
                 if m in REQUIRED_METHODS and callable(f)
                 and self._is_not_implemented_stub(f)}
        for d in SUBJECT_DIRS:
            subject_dir = os.path.join(SUBJECTS_ROOT, d)
            mod = _load_subject(subject_dir)
            for m in stubs:
                impl = getattr(mod.SubjectApp, m)
                self.assertNotEqual(
                    impl.__qualname__.split(".")[0], "BaseSubjectApp",
                    f"{d} 未覆盖基类接口 {m}（仍是 NotImplementedError stub）")

    @staticmethod
    def _is_not_implemented_stub(func):
        try:
            return "raise NotImplementedError" in inspect.getsource(func)
        except OSError:
            return False

    def test_metadata_attrs_present(self):
        for d in SUBJECT_DIRS:
            subject_dir = os.path.join(SUBJECTS_ROOT, d)
            mod = _load_subject(subject_dir)
            app = mod.SubjectApp(subject_dir)
            self.assertTrue(app.name, f"{d} name 为空")
            self.assertTrue(app.LEVEL, f"{d} LEVEL 为空")
            self.assertTrue(app.SUBJECT, f"{d} SUBJECT 为空")
            self.assertEqual(app.version, "v3.0", f"{d} version 异常")

    def test_max_tool_loops_positive_int(self):
        for d in SUBJECT_DIRS:
            subject_dir = os.path.join(SUBJECTS_ROOT, d)
            mod = _load_subject(subject_dir)
            app = mod.SubjectApp(subject_dir)
            loops = app.get_max_tool_loops()
            self.assertIsInstance(loops, int, f"{d} get_max_tool_loops 非 int")
            self.assertGreaterEqual(loops, 0, f"{d} get_max_tool_loops < 0")
            if app.tools:
                # 有工具时必须提供循环配额，否则工具永远用不上
                self.assertGreater(loops, 0, f"{d} 有工具但 max_loops=0，工具静默失效")


class TestQuestionPromptToolInstructions(unittest.TestCase):
    """回归：非 ReAct 模式下，有工具的学科提示词必须包含工具指令。

    修复前高中化学非 ReAct 分支直接返回 config 行，7 个工具模型永远不会调用。
    """

    def test_non_react_prompt_contains_tool_instructions_when_tools_exist(self):
        for d in SUBJECT_DIRS:
            subject_dir = os.path.join(SUBJECTS_ROOT, d)
            mod = _load_subject(subject_dir)
            app = mod.SubjectApp(subject_dir)
            app.react_mode = False  # 强制非 ReAct
            prompt = app.get_question_prompt()
            self.assertIsInstance(prompt, str, f"{d} 提示词非 str")
            self.assertTrue(prompt.strip(), f"{d} 非 ReAct 提示词为空")
            if app.tools:
                instructions = app.get_tool_instructions()
                if instructions:
                    self.assertIn(instructions[:80], prompt,
                                  f"{d} 非 ReAct 提示词缺少工具指令（工具静默失效）")

    def test_react_prompt_different_from_non_react(self):
        """ReAct 模式（agent_prompt_lines）与 非 ReAct 提示词不同源"""
        for d in SUBJECT_DIRS:
            subject_dir = os.path.join(SUBJECTS_ROOT, d)
            mod = _load_subject(subject_dir)
            app = mod.SubjectApp(subject_dir)
            app.react_mode = True
            react_prompt = app.get_question_prompt()
            app.react_mode = False
            plain_prompt = app.get_question_prompt()
            if app.config.get("agent_prompt_lines"):
                self.assertNotEqual(react_prompt, plain_prompt,
                                    f"{d} ReAct/非 ReAct 提示词完全相同，模式切换无效")

    def test_chemistry_has_tools_in_non_react(self):
        """化学非 ReAct 必须有工具指令（本回归的原始场景）"""
        subject_dir = os.path.join(SUBJECTS_ROOT, "高中化学v3.0")
        mod = _load_subject(subject_dir)
        app = mod.SubjectApp(subject_dir)
        app.react_mode = False
        self.assertTrue(app.tools, "化学学科应构建工具")
        prompt = app.get_question_prompt()
        self.assertIn(app.get_tool_instructions()[:80], prompt)


class TestRealConfigsValid(unittest.TestCase):
    """7 个学科真实 config.json 必须通过 schema 校验"""

    def test_all_real_configs_pass_validation(self):
        from core.config_schema import validate_config
        for d in SUBJECT_DIRS:
            subject_dir = os.path.join(SUBJECTS_ROOT, d)
            config = validate_config(subject_dir)
            self.assertIsInstance(config, dict, f"{d} config 校验失败")
            self.assertTrue(config.get("question_prompt_lines"),
                            f"{d} question_prompt_lines 为空")


class TestPackagingResources(unittest.TestCase):
    """H3 回归：打包资源必须包含 agent_prompt.json，且首次运行会复制到 exe 同级"""

    def test_all_subjects_have_agent_prompt_file(self):
        for d in SUBJECT_DIRS:
            agent_prompt = os.path.join(SUBJECTS_ROOT, d, "agent_prompt.json")
            self.assertTrue(os.path.isfile(agent_prompt),
                            f"{d} 缺少 agent_prompt.json")

    def test_main_ensure_config_copies_agent_prompt(self):
        for d in SUBJECT_DIRS:
            main_path = os.path.join(SUBJECTS_ROOT, d, "main.py")
            with open(main_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn('"agent_prompt.json"', content,
                          f"{d}/main.py 的 _ensure_config 未复制 agent_prompt.json")

    def test_spec_datas_include_agent_prompt(self):
        spec_dir = os.path.join(REPO_ROOT, "specs")
        specs = [f for f in os.listdir(spec_dir) if f.endswith(".spec")]
        self.assertTrue(specs, "仓库应有至少一个 PyInstaller spec")
        for spec_name in specs:
            with open(os.path.join(spec_dir, spec_name), encoding="utf-8") as f:
                content = f.read()
            self.assertIn("agent_prompt.json", content,
                          f"{spec_name} datas 缺少 agent_prompt.json")


class TestMathSubjectDir(unittest.TestCase):
    """回归：小学数学 main.py 的 subject_dir 解析。

    修复前无条件返回 sys.executable 目录（开发时指向 Python 解释器目录），
    config.json/.env 被写到错误位置；修复后与其余 6 科一致。
    """

    def test_subject_dir_resolves_to_subject_folder(self):
        main_dir = os.path.join(SUBJECTS_ROOT, "小学数学v3.0")
        spec = importlib.util.spec_from_file_location(
            "math_main", os.path.join(main_dir, "main.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        subject_dir = mod._get_subject_dir()
        self.assertEqual(os.path.abspath(subject_dir).rstrip("/"),
                         os.path.abspath(main_dir).rstrip("/"))
        self.assertTrue(os.path.exists(os.path.join(subject_dir, "config.json")))

    def test_other_subjects_have_resource_path(self):
        """其余 6 科均提供打包感知的 _get_resource_path（小学数学此前也缺此模式）"""
        for d in SUBJECT_DIRS:
            main_path = os.path.join(SUBJECTS_ROOT, d, "main.py")
            with open(main_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("_get_resource_path", content, f"{d}/main.py 缺少资源路径解析")


if __name__ == "__main__":
    unittest.main()
