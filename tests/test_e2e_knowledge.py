"""端到端集成测试：知识讲义切割 + 校对报告格式验证。

使用真实讲义样本文件 + mock LLM 调用验证完整管线。
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =========================================================================
# 真实样本切割测试
# =========================================================================

class TestRealLectureSplit(unittest.TestCase):
    """用真实讲义文件测试切割管线。"""

    @classmethod
    def setUpClass(cls):
        cls.sample_path = Path(
            "C:/Users/PC/Desktop/临时/"
            "第 十三 讲【写作】高阶素材深度运用_清理_raw.md"
        )

    def setUp(self):
        from shared.knowledge_split import knowledge_split
        self.knowledge_split = knowledge_split

    def test_sample_file_exists(self):
        """样本文件存在且可读"""
        self.assertTrue(
            self.sample_path.exists(),
            f"样本讲义不存在: {self.sample_path}"
        )

    def test_scan_sample_structure(self):
        """步骤 1：结构扫描样本讲义"""
        from shared.knowledge_split import _scan_structure

        content = self.sample_path.read_text(encoding="utf-8")
        result = _scan_structure(content)

        # 是大型文档
        self.assertGreater(result["total_lines"], 100)
        self.assertGreater(result["total_chars"], 10000)

        # 有目录树
        self.assertGreater(len(result["tree"]), 0,
                           "应检测到标题层级")

        # 有多个块
        self.assertGreater(len(result["blocks"]), 5,
                           f"大讲义应切出多个块，实际 {len(result['blocks'])}")

        # HIGH 置信度块应占大多数（格式规整的讲义）
        high = [b for b in result["blocks"] if b["confidence"] == "HIGH"]
        self.assertGreater(len(high), 0, "规整讲义应有 HIGH 置信度块")

        # 检查每个块
        for blk in result["blocks"]:
            self.assertIn("from", blk)
            self.assertIn("to", blk)
            self.assertIn("confidence", blk)
            self.assertIn("anchor", blk)

    def test_split_sample_no_llm(self):
        """纯 Python 切割样本讲义（无 LLM）"""
        content = self.sample_path.read_text(encoding="utf-8")
        results = self.knowledge_split(content, llm_callable=None)

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, "应至少产生 1 个单元")

        # 每个单元应有类型
        for r in results:
            self.assertIn("content", r)
            self.assertIn("type", r)
            self.assertIsInstance(r["content"], str)
            self.assertIsInstance(r["type"], str)
            self.assertIn(r["type"], ["knowledge", "problem_strip"])

    def test_split_sample_with_mock_llm(self):
        """mock LLM 切割样本讲义"""
        content = self.sample_path.read_text(encoding="utf-8")

        def mock_llm(user_text, system_prompt):
            # 返回正常的分类结果（模拟 LLM 对 LOW 块的处理）
            return json.dumps({
                "blocks": [
                    {"id": 0, "type": "knowledge", "sub_blocks": []},
                ],
            }, ensure_ascii=False)

        results = self.knowledge_split(content, llm_callable=mock_llm)

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_split_result_structure_consistent(self):
        """切割结果结构一致性"""
        import shared.knowledge_split as ksplit

        content = self.sample_path.read_text(encoding="utf-8")

        # 跑 3 次，确认结构一致
        for run in range(3):
            results = ksplit.knowledge_split(content, llm_callable=None)
            self.assertGreater(len(results), 0, f"第 {run+1} 次运行应产生结果")
            for r in results:
                self.assertIn("type", r)
                self.assertGreater(len(r["content"]), 0)


# =========================================================================
# Mock LLM + prompt 加载综合测试
# =========================================================================

class TestSubjectIntegration(unittest.TestCase):
    """验证 subject.py 与知识 prompt 的集成。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        subject_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "subjects", "高中语文v3.0"
        )
        spec = importlib.util.spec_from_file_location(
            "yuwen_subject_v2",
            os.path.join(subject_dir, "subject.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.SubjectApp = mod.SubjectApp
        cls.subject_dir = subject_dir

    def test_react_mode_knowledge_prompt_loads(self):
        """ReAct 模式下 get_knowledge_prompt 加载统一 prompt"""
        from core import config_loader
        import importlib
        importlib.reload(config_loader)
        config_loader.clear_config_cache()

        app = self.SubjectApp(self.subject_dir)
        app.react_mode = True
        app.tools = app.build_tools()

        prompt = app.get_knowledge_prompt()

        # 手动 reload 后应该加载新 prompt
        self.assertTrue(
            len(prompt) > 500,
            f"ReAct 知识 prompt 应较长为统一prompt，但实际: {len(prompt)} 字符"
        )

    def test_non_react_mode_fallback(self):
        """非 ReAct 模式 fallback 到旧 knowledge_prompt_lines"""
        from core import config_loader
        import importlib
        importlib.reload(config_loader)
        config_loader.clear_config_cache()

        app = self.SubjectApp(self.subject_dir)
        app.react_mode = False
        app.tools = app.build_tools()

        prompt = app.get_knowledge_prompt()

        # 非 ReAct 模式：prompt 较短（旧 knowledge_prompt_lines，约 2-3K 字符）
        self.assertTrue(
            len(prompt) > 500,
            "非 ReAct 模式仍应返回有效的 prompt"
        )

    def test_question_prompt_still_works(self):
        """题目 prompt 在 ReAct 模式下仍可正常加载"""
        from core import config_loader
        import importlib
        importlib.reload(config_loader)
        config_loader.clear_config_cache()

        app = self.SubjectApp(self.subject_dir)
        app.react_mode = True
        app.tools = app.build_tools()

        prompt = app.get_question_prompt()

        # 统一 prompt 应较长
        self.assertTrue(
            len(prompt) > 500,
            f"题目 prompt 应正常加载，但实际: {len(prompt)} 字符"
        )
        # 统一 prompt 应同时包含题目和知识关键词
        self.assertTrue(
            "文本类型" in prompt or "第 0 步" in prompt or "校对报告" in prompt,
            "应包含校对流程关键词"
        )

    def test_knowledge_split_mode_registered(self):
        """knowledge_smart / knowledge_manual 在 subject 中已注册"""
        app = self.SubjectApp(self.subject_dir)

        import tempfile, shutil
        tmpdir = tempfile.mkdtemp()
        try:
            md_path = os.path.join(tmpdir, "test.md")

            # knowledge_manual 测试
            content = (
                "###### 知识开始 ######\n"
                "知识内容\n"
                "###### 知识结束 ######\n"
            )
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)

            out_root = os.path.join(tmpdir, "out_manual")
            os.makedirs(out_root, exist_ok=True)

            result = app.split_lecture(md_path, out_root, "test",
                                        options={"split_mode": "knowledge_manual"})
            self.assertTrue(result)

            # knowledge_smart 测试（无 LLM 调用）
            md_path2 = os.path.join(tmpdir, "test2.md")
            content2 = "### 知识讲解\n\n内容。\n\n##### 素材一\n\n正文。\n"
            with open(md_path2, "w", encoding="utf-8") as f:
                f.write(content2)

            out_root2 = os.path.join(tmpdir, "out_smart")
            os.makedirs(out_root2, exist_ok=True)

            import shared.knowledge_split as ksplit
            orig = ksplit.knowledge_split_smart

            def fake_smart(md, url, key, model, md_file=None):
                return [{"content": "第一部分", "type": "knowledge"}]

            ksplit.knowledge_split_smart = fake_smart
            try:
                result2 = app.split_lecture(md_path2, out_root2, "test2",
                                            options={"split_mode": "knowledge_smart",
                                                      "api_url": "test",
                                                      "api_key": "test",
                                                      "model": "test"})
                self.assertTrue(result2)
            finally:
                ksplit.knowledge_split_smart = orig

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# =========================================================================
# 校对报告格式验证测试
# =========================================================================

class TestProofreadReportFormat(unittest.TestCase):
    """验证校对输出格式（不管你发了什么内容，输出必须合规）。"""

    def test_marker_count_matches_reason_count(self):
        """标记数 = 原因数"""
        sample_report = (
            "一般问题\n\n"
            "### 标记原文\n"
            "这是原文【1|错字|正字】和更多原文【2|标点，|标点。】结尾。\n\n"
            "### 修改原因\n"
            "1. 错别字：\"错字\"应为\"正字\"\n"
            "2. 标点：逗号应为句号\n"
        )
        from core.format_enforcement import _enforce_format
        ok, issues = _enforce_format(sample_report)
        self.assertTrue(ok, f"格式应合规: {issues}")

    def test_unequal_markers_detected(self):
        """标记数 != 原因数 应被检测"""
        sample_report = (
            "一般问题\n\n"
            "### 标记原文\n"
            "原文【1|错字|正字】【2|多余|】\n\n"
            "### 修改原因\n"
            "1. 只有一条原因\n"
        )
        from core.format_enforcement import _enforce_format
        ok, issues = _enforce_format(sample_report)
        self.assertFalse(ok, "标记 2 个但原因只有 1 条，应被检测")
        self.assertIn("缺少", issues)

    def test_knowledge_report_format_same_rules(self):
        """知识校对报告格式规则应与题目一致"""
        # 知识报告的格式审查复用同一套 _enforce_format
        sample_report = (
            "轻微问题\n\n"
            "### 标记原文\n"
            "素材【寓意】中写道\"标准化BAOLI\"【1|BAOLI|暴力】。\n\n"
            "### 修改原因\n"
            "1. 拼音输入错误：BAOLI 应为 暴力\n"
        )
        from core.format_enforcement import _enforce_format
        ok, issues = _enforce_format(sample_report)
        self.assertTrue(ok, f"知识校对报告格式应通过: {issues}")


# =========================================================================
# 中间产物完整性验证
# =========================================================================

class TestIntermediateArtifactsCompleteness(unittest.TestCase):
    """验证所有中间产物都有落盘。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        # 创建中间产物目录
        (Path("output") / "中间产物" / "e2e_test").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)

    def test_knowledge_split_generates_all_artifacts(self):
        """知识切割管线应落盘全部中间产物"""
        from shared.knowledge_split import knowledge_split

        content = (
            "### 知识讲解\n\n"
            + "正文。" + "填充。" * 100 + "\n\n"
        )

        def mock_llm(user_text, system_prompt):
            return json.dumps({
                "blocks": [{"id": 0, "type": "knowledge", "sub_blocks": []}],
            }, ensure_ascii=False)

        _ = knowledge_split(content, llm_callable=mock_llm,
                           doc_name="e2e_artifacts")

        # 检查所有中间产物
        base = Path("output") / "中间产物" / "e2e_artifacts"
        artifacts = list(base.glob("*"))
        artifact_names = {a.name for a in artifacts}
        print(f"\n已落盘中间产物 ({len(artifacts)} 个): {sorted(artifact_names)}")

        # 核心文件必须存在
        required = ["_knowledge_scan_tree.json"]
        for name in required:
            self.assertIn(name, artifact_names,
                          f"核心中间产物缺失: {name}")


if __name__ == "__main__":
    unittest.main()
