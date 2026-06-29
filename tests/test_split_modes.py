import unittest
import sys
import os
import tempfile
import shutil
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_subject():
    subject_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "subjects", "高中语文v3.0"
    )
    spec = importlib.util.spec_from_file_location(
        "yuwen_subject",
        os.path.join(subject_dir, "subject.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SubjectApp, subject_dir


SubjectApp, SUBJECT_DIR = _load_subject()


class TestSplitModesExam(unittest.TestCase):
    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_md(self, content, name="test.md"):
        path = os.path.join(self.tmpdir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_split_mode_none_single_unit(self):
        md_content = "第一部分\n1. 题目一\n2. 题目二\n3. 题目三"
        md_path = self._make_md(md_content)
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        self.app.split_exam(md_path, out_root, "test_paper", options={"split_mode": "none"})

        paper_dir = os.path.join(out_root, "test_paper")
        self.assertTrue(os.path.exists(paper_dir))
        q_dirs = [d for d in os.listdir(paper_dir) if os.path.isdir(os.path.join(paper_dir, d))]
        self.assertEqual(len(q_dirs), 1)
        q_dir = os.path.join(paper_dir, q_dirs[0])
        # 仅计题目主文件，排除前置搜索用的 _clean.md 辅助副本
        md_files = [f for f in os.listdir(q_dir) if f.endswith(".md") and not f.endswith("_clean.md")]
        self.assertEqual(len(md_files), 1)

    def test_split_mode_rule_default(self):
        md_content = "1．第一题内容\n\n2．第二题内容\n\n3．第三题内容"
        md_path = self._make_md(md_content)
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        self.app.split_exam(md_path, out_root, "test_paper", options={"split_mode": "rule"})

        paper_dir = os.path.join(out_root, "test_paper")
        q_dirs = [d for d in os.listdir(paper_dir) if os.path.isdir(os.path.join(paper_dir, d))]
        self.assertGreaterEqual(len(q_dirs), 2)

    def test_split_mode_manual_markers(self):
        md_content = (
            "开头\n"
            "###### 题目开始 ######\n"
            "第一题正文\n"
            "###### 题目结束 ######\n"
            "中间\n"
            "###### 题目开始 ######\n"
            "第二题正文\n"
            "###### 题目结束 ######\n"
            "结尾\n"
        )
        md_path = self._make_md(md_content)
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        self.app.split_exam(md_path, out_root, "test_paper", options={"split_mode": "manual"})

        paper_dir = os.path.join(out_root, "test_paper")
        q_dirs = sorted([d for d in os.listdir(paper_dir) if os.path.isdir(os.path.join(paper_dir, d))])
        self.assertEqual(len(q_dirs), 2)
        for qd in q_dirs:
            q_dir = os.path.join(paper_dir, qd)
            # 仅计题目主文件，排除前置搜索用的 _clean.md 辅助副本
            md_files = [f for f in os.listdir(q_dir) if f.endswith(".md") and not f.endswith("_clean.md")]
            self.assertEqual(len(md_files), 1)

    def test_split_mode_none_output_consistent(self):
        md_content = "测试内容"
        md_path = self._make_md(md_content)
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        self.app.split_exam(md_path, out_root, "test_paper", options={"split_mode": "none"})

        paper_dir = os.path.join(out_root, "test_paper")
        q_dirs = [d for d in os.listdir(paper_dir) if d.startswith("第") and d.endswith("题")]
        self.assertEqual(len(q_dirs), 1)

    def test_default_split_mode_is_rule(self):
        md_content = "1．第一题\n\n2．第二题"
        md_path = self._make_md(md_content)
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        self.app.split_exam(md_path, out_root, "test_paper", options={})

        paper_dir = os.path.join(out_root, "test_paper")
        q_dirs = [d for d in os.listdir(paper_dir) if os.path.isdir(os.path.join(paper_dir, d))]
        self.assertGreaterEqual(len(q_dirs), 2)

    def test_split_mode_smart_with_mock(self):
        md_content = "一些内容"
        md_path = self._make_md(md_content)
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        import shared.smart_split as smart_mod
        orig = smart_mod.smart_split

        def fake_smart(md, url, key, model, md_file=None):
            return [{"content": "第一部分"}, {"content": "第二部分"}]

        smart_mod.smart_split = fake_smart
        try:
            self.app.split_exam(md_path, out_root, "test_paper", options={
                "split_mode": "smart",
                "api_url": "test",
                "api_key": "test",
                "model": "test",
            })
        finally:
            smart_mod.smart_split = orig

        paper_dir = os.path.join(out_root, "test_paper")
        q_dirs = sorted([d for d in os.listdir(paper_dir) if d.startswith("第") and d.endswith("题")])
        self.assertEqual(len(q_dirs), 2)

    def test_all_modes_same_output_structure(self):
        md_content = "1．题目一\n\n2．题目二"
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        for mode in ["rule", "none"]:
            mode_dir = os.path.join(out_root, mode)
            os.makedirs(mode_dir, exist_ok=True)
            md_path = self._make_md(md_content, name=f"{mode}.md")
            mode_out = os.path.join(self.tmpdir, f"out_{mode}")
            os.makedirs(mode_out, exist_ok=True)
            self.app.split_exam(md_path, mode_out, f"paper_{mode}", options={"split_mode": mode})

            paper_dir = os.path.join(mode_out, f"paper_{mode}")
            self.assertTrue(os.path.exists(paper_dir))
            q_dirs = [d for d in os.listdir(paper_dir) if d.startswith("第") and d.endswith("题")]
            self.assertGreaterEqual(len(q_dirs), 1)
            for qd in q_dirs:
                q_dir = os.path.join(paper_dir, qd)
                self.assertTrue(os.path.isdir(q_dir))
                # 仅计题目主文件，排除前置搜索用的 _clean.md 辅助副本
                md_files = [f for f in os.listdir(q_dir) if f.endswith(".md") and not f.endswith("_clean.md")]
                self.assertEqual(len(md_files), 1)


class TestSplitModesLecture(unittest.TestCase):
    def setUp(self):
        self.app = SubjectApp(SUBJECT_DIR)
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_md(self, content, name="test.md"):
        path = os.path.join(self.tmpdir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_lecture_split_mode_none(self):
        md_content = "# 标题\n\n内容一\n\n内容二"
        md_path = self._make_md(md_content)
        out_root = os.path.join(self.tmpdir, "output")
        os.makedirs(out_root, exist_ok=True)

        result = self.app.split_lecture(md_path, out_root, "test_lec", options={"split_mode": "none"})
        self.assertTrue(result)


class TestKnowledgeManualMarker(unittest.TestCase):
    """测试知识手工标记（###### 知识开始/结束 ######）"""

    def test_knowledge_marker_basic(self):
        from core.manual_split import split_by_knowledge_markers
        content = (
            "开头\n"
            "###### 知识开始 ######\n"
            "第一块知识\n"
            "###### 知识结束 ######\n"
            "结尾\n"
        )
        results = split_by_knowledge_markers(content)
        self.assertEqual(len(results), 1)
        self.assertIn("第一块知识", results[0]["content"])

    def test_knowledge_marker_multiple(self):
        from core.manual_split import split_by_knowledge_markers
        content = (
            "开头\n"
            "###### 知识开始 ######\n"
            "块一\n"
            "###### 知识结束 ######\n"
            "中间\n"
            "###### 知识开始 ######\n"
            "块二\n"
            "###### 知识结束 ######\n"
            "结尾\n"
        )
        results = split_by_knowledge_markers(content)
        self.assertEqual(len(results), 2)
        self.assertIn("块一", results[0]["content"])
        self.assertIn("块二", results[1]["content"])

    def test_knowledge_marker_unpaired_start(self):
        from core.manual_split import split_by_knowledge_markers, KnowledgeMarkerError
        content = (
            "###### 知识开始 ######\n"
            "内容\n"
        )
        with self.assertRaises(KnowledgeMarkerError):
            split_by_knowledge_markers(content)

    def test_knowledge_marker_unpaired_end(self):
        from core.manual_split import split_by_knowledge_markers, KnowledgeMarkerError
        content = (
            "内容\n"
            "###### 知识结束 ######\n"
        )
        with self.assertRaises(KnowledgeMarkerError):
            split_by_knowledge_markers(content)

    def test_knowledge_marker_no_markers(self):
        from core.manual_split import split_by_knowledge_markers, KnowledgeMarkerError
        content = "只是普通文本，没有任何标记"
        with self.assertRaises(KnowledgeMarkerError):
            split_by_knowledge_markers(content)

    def test_knowledge_marker_empty_block(self):
        from core.manual_split import split_by_knowledge_markers
        content = (
            "###### 知识开始 ######\n"
            "\n"
            "###### 知识结束 ######\n"
        )
        results = split_by_knowledge_markers(content)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content"].strip(), "")

    def test_knowledge_and_problem_markers_independent(self):
        """知识标记和题目标记互不干扰"""
        from core.manual_split import split_by_knowledge_markers, split_by_manual_markers
        content = (
            "###### 知识开始 ######\n"
            "知识内容\n"
            "###### 题目开始 ######\n"
            "嵌入题目\n"
            "###### 题目结束 ######\n"
            "更多知识\n"
            "###### 知识结束 ######\n"
        )
        knowledge_results = split_by_knowledge_markers(content)
        self.assertEqual(len(knowledge_results), 1)
        self.assertIn("嵌入题目", knowledge_results[0]["content"])

        # 题目标记也能独立解析
        problem_only = (
            "###### 题目开始 ######\n"
            "单独题目\n"
            "###### 题目结束 ######\n"
        )
        problem_results = split_by_manual_markers(problem_only)
        self.assertEqual(len(problem_results), 1)
        self.assertIn("单独题目", problem_results[0]["content"])


if __name__ == "__main__":
    unittest.main()
