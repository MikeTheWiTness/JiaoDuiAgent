import unittest
import sys
import os
import importlib.util
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_subject_module():
    subject_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "subjects", "高中语文v3.0"
    )
    spec = importlib.util.spec_from_file_location(
        "gaozhong_yuwen_subject",
        os.path.join(subject_dir, "subject.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, subject_dir


SubjectMod, SUBJECT_DIR = _load_subject_module()
SubjectApp = SubjectMod.SubjectApp


class TestSubjectAppInterface(unittest.TestCase):
    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)

    def test_version_is_v3(self):
        self.assertEqual(self.app.version, "v3.0")

    def test_name_is_correct(self):
        self.assertEqual(self.app.name, "高中语文")

    def test_level_and_subject_attrs(self):
        self.assertEqual(self.app.LEVEL, "高中")
        self.assertEqual(self.app.SUBJECT, "语文")

    def test_get_tool_instructions_no_args(self):
        result = self.app.get_tool_instructions()
        self.assertIsInstance(result, str)

    def test_get_question_prompt_includes_core_content(self):
        prompt = self.app.get_question_prompt()
        self.assertIn("校对", prompt)
        self.assertIn("批注", prompt)
        self.assertIn("标记原文", prompt)

    def test_get_knowledge_prompt_includes_core_content(self):
        prompt = self.app.get_knowledge_prompt()
        self.assertIn("校对", prompt)
        self.assertIn("标记原文", prompt)


class TestSubjectAppMethodSignatures(unittest.TestCase):
    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)

    def test_split_lecture_signature(self):
        import inspect
        sig = inspect.signature(self.app.split_lecture)
        params = list(sig.parameters.keys())
        self.assertEqual(params[:4], ["md_file", "output_root", "base_name", "options"])

    def test_split_exam_signature(self):
        import inspect
        sig = inspect.signature(self.app.split_exam)
        params = list(sig.parameters.keys())
        self.assertEqual(params[:3], ["md_file", "output_root", "base_name"])

    def test_generate_knowledge_signature(self):
        import inspect
        sig = inspect.signature(self.app.generate_knowledge)
        params = list(sig.parameters.keys())
        self.assertEqual(params[:3], ["md_file", "output_root", "base_name"])

    def test_proofread_one_signature(self):
        import inspect
        sig = inspect.signature(self.app.proofread_one)
        params = list(sig.parameters.keys())
        self.assertEqual(params[:4], [
            "ctx", "q_dir", "q_name", "generate_pdf"
        ])

    def test_post_proofread_hook_signature(self):
        import inspect
        sig = inspect.signature(self.app.post_proofread_hook)
        params = list(sig.parameters.keys())
        self.assertEqual(params[:2], ["result", "q_dir"])

    def test_pre_proofread_hook_signature(self):
        import inspect
        sig = inspect.signature(self.app.pre_proofread_hook)
        params = list(sig.parameters.keys())
        self.assertEqual(params[:1], ["md_text"])


class TestAppCleanPathHack(unittest.TestCase):
    def test_app_py_no_path_hack(self):
        app_path = os.path.join(SUBJECT_DIR, "app.py")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn("replace(r'subjects", content)
        self.assertNotIn("sys.path[0]", content)


if __name__ == "__main__":
    unittest.main()
