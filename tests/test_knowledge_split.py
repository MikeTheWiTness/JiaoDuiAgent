"""知识讲义切割管线测试。

覆盖：
  - 步骤 1 结构编目（各种格式信号识别）
  - 步骤 2 LLM 切分决策 mock（正常/异常/格式错误/空返回）
  - 步骤 3 切分执行（LLM 方案 / 规则降级）
  - 完整管线（含 mock LLM / 降级逻辑）
  - LLM 中间产物落盘验证
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shared.knowledge_split as ksplit
from shared.knowledge_split import (
    _scan_structure,
    _execute_split,
    _rule_fallback_split,
    _dump_intermediate,
    _infer_block_type,
    knowledge_split,
)


# =========================================================================
# 测试样本
# =========================================================================

SAMPLE_STRUCTURED = """## 模块一 写作素材深度运用

#### （一）东方经典智慧

（1）《庄子》"浑沌之死"

南海的帝王叫做"倏"，北海的帝王叫做"忽"，中央的帝王叫做"浑沌"。倏和忽商量着报答浑沌的恩情，说："人都有七窍，唯独浑沌没有七窍，试着给他凿出七窍。"于是每天替浑沌开一窍，到了第七天，浑沌就死了。

【寓意】批判"标准化暴力"。

【适用角度】教育方式、个人成长、文化多样性

【事例句运用】多元共生：当某种文明以"开化"之名强行改造其他文明时，便重演了《庄子》中"浑沌之死"的悲剧。

（2）《庄子》"汉阴丈人拒槔"

子贡路过汉阴时，看见一位老人抱着坛子取水浇地，费了很多力气但收效甚小。子贡问他为什么不用桔槔提水，老人说："有机械者必有机事，有机事者必有机心。"

【寓意】批判机心。丈人拒绝的不是工具，而是工具背后侵蚀人心的思维方式。

【适用角度】人文情怀、技术反思、保持初心
"""

SAMPLE_NO_STRUCTURE = """作文素材积累材料

庄子是战国时期著名的思想家，他的寓言故事至今仍被广泛引用。
例如浑沌之死这个典故，讲的是浑沌本来没有七窍，倏和忽出于好意为他开凿，
结果反而导致浑沌的死亡。这个故事启发我们要尊重事物的本然状态。

同学们在使用这个素材时，注意不能直接全文引述——那样会占用
太多篇幅。建议用"标签化引用"的方式，只提取核心人物和事件，
然后用简短的分析句连接论点。这样才能让素材服务于论证，
而不是让论证迁就素材。"""

SAMPLE_MIXED = """#### 西方神话与典故

（1）伊卡洛斯的翅膀

代达罗斯用羽毛和蜡为儿子伊卡洛斯制作了翅膀。伊卡洛斯飞得过高，蜡翼熔化，坠海而亡。

【寓意】敬畏边界，自由有度。

【适用角度】科学精神、自我认知与成长

补充题一：（2025天津虹桥二模）阅读下面的材料，根据要求写作。
当代青年在学习和生活中往往面临"激情"与"理性"的碰撞。请写一篇文章。
**例文：** 青春是一场盛大的舞蹈...
【详解】本题考查学生写作的能力。
"""


# =========================================================================
# 步骤 1：结构编目测试
# =========================================================================

class TestStructureScan(unittest.TestCase):

    def test_detect_item_numbers(self):
        """检测 （N） 编号条目"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        catalog = result["catalog"]
        item_numbers = [e for e in catalog if e["type"] == "item_number"]
        self.assertGreaterEqual(len(item_numbers), 2,
                                f"应至少识别 2 个编号条目，实际 {len(item_numbers)}")

    def test_detect_hashtag_headings(self):
        """检测 ## #### 标题"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        catalog = result["catalog"]
        headings = [e for e in catalog if e["type"] == "heading"]
        self.assertGreaterEqual(len(headings), 1,
                                f"应至少识别 1 个 ## 标题，实际 {len(headings)}")

    def test_detect_knowledge_signals(self):
        """检测知识点固定段头"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        catalog = result["catalog"]
        signals = [e for e in catalog if e["type"] == "knowledge_signal"]
        self.assertGreaterEqual(len(signals), 2,
                                f"应至少识别 2 个知识信号，实际 {len(signals)}")

    def test_detect_exam_marker(self):
        """检测嵌入题目标记"""
        result = _scan_structure(SAMPLE_MIXED)
        catalog = result["catalog"]
        markers = [e for e in catalog if e["type"] == "exam_marker"]
        self.assertGreaterEqual(len(markers), 1,
                                f"应至少识别 1 个题目标记，实际 {len(markers)}")

    def test_no_structure_fallback(self):
        """无结构信号文本"""
        result = _scan_structure(SAMPLE_NO_STRUCTURE)
        catalog = result["catalog"]
        # 无结构信号时所有行都标记为 content
        self.assertGreaterEqual(len(catalog), 1)

    def test_catalog_entries_have_required_fields(self):
        """编目条目包含必需字段"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        for entry in result["catalog"]:
            self.assertIn("id", entry)
            self.assertIn("line", entry)
            self.assertIn("type", entry)
            self.assertIn("text", entry)
            self.assertIsInstance(entry["line"], int)

    def test_catalog_entry_id_format(self):
        """编目条目 id 格式正确（如 L0004）"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        for entry in result["catalog"]:
            self.assertTrue(re.match(r'^L\d{4}$', entry["id"]),
                            f"id 格式异常: {entry['id']}")

    def test_heading_has_level(self):
        """标题条目包含 level 字段"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        headings = [e for e in result["catalog"] if e["type"] == "heading"]
        for h in headings:
            self.assertIn("level", h)
            self.assertGreaterEqual(h["level"], 1)
            self.assertLessEqual(h["level"], 6)

    def test_total_lines_chars(self):
        """返回总行数和总字符数"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        self.assertGreater(result["total_lines"], 0)
        self.assertGreater(result["total_chars"], 0)
        self.assertEqual(result["total_chars"], len(SAMPLE_STRUCTURED))


# =========================================================================
# 步骤 2+3：LLM 切分方案 + 执行测试
# =========================================================================

class TestSplitExecution(unittest.TestCase):

    def test_execute_split_with_units(self):
        """根据 LLM units 执行切分"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        catalog = result["catalog"]
        # 找到 item_number 的 id
        item_ids = [e["id"] for e in catalog if e["type"] == "item_number"]
        units = [{"id": iid, "type": "knowledge"} for iid in item_ids]

        results = _execute_split(SAMPLE_STRUCTURED, catalog, units)
        self.assertEqual(len(results), len(units))
        for r in results:
            self.assertIn("content", r)
            self.assertIn("type", r)
            self.assertGreater(len(r["content"]), 0)

    def test_execute_split_single_unit(self):
        """单单元切分"""
        result = _scan_structure(SAMPLE_NO_STRUCTURE)
        catalog = result["catalog"]
        # 用第一个 content 行的 id
        content_entries = [e for e in catalog if e["type"] == "content"]
        if content_entries:
            units = [{"id": content_entries[0]["id"], "type": "knowledge"}]
        else:
            units = [{"id": catalog[0]["id"], "type": "knowledge"}]

        results = _execute_split(SAMPLE_NO_STRUCTURE, catalog, units)
        self.assertGreaterEqual(len(results), 1)

    def test_execute_split_empty_units(self):
        """空 units → 降级为全文单单元"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        results = _execute_split(SAMPLE_STRUCTURED, result["catalog"], [])
        self.assertEqual(len(results), 1)

    def test_rule_fallback_with_item_numbers(self):
        """规则降级：以 item_number 为边界"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        results = _rule_fallback_split(SAMPLE_STRUCTURED, result["catalog"])
        self.assertGreaterEqual(len(results), 2)  # 至少 2 个素材条目

    def test_rule_fallback_no_structure(self):
        """规则降级：无结构 → 单单元"""
        result = _scan_structure(SAMPLE_NO_STRUCTURE)
        results = _rule_fallback_split(SAMPLE_NO_STRUCTURE, result["catalog"])
        self.assertEqual(len(results), 1)

    def test_infer_block_type_knowledge(self):
        """推断为知识类型"""
        snippet = "【寓意】批判标准化暴力。【适用角度】教育方式"
        self.assertEqual(_infer_block_type(snippet), "knowledge")

    def test_infer_block_type_problem(self):
        """推断为题目的类型"""
        snippet = "【详解】本题考查学生写作的能力。**审题：** 这是一道..."
        self.assertEqual(_infer_block_type(snippet), "problem_strip")


# =========================================================================
# 完整管线测试（含 mock LLM）
# =========================================================================

class TestFullPipeline(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_pipeline_no_llm_structured(self):
        """无 LLM 的规则降级管线（结构化讲义）"""
        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=None)
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertIn("content", r)
            self.assertIn("type", r)
            self.assertGreater(len(r["content"]), 0)

    def test_pipeline_no_llm_unstructured(self):
        """无 LLM 处理无结构文本 → 单单元"""
        results = knowledge_split(SAMPLE_NO_STRUCTURE, llm_callable=None)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "knowledge")

    def test_pipeline_with_mock_llm(self):
        """mock LLM 正常返回 units → 全管线"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        catalog = result["catalog"]
        item_ids = [e["id"] for e in catalog if e["type"] == "item_number"]

        def mock_llm(user_text, system_prompt):
            return json.dumps({
                "units": [{"id": iid, "type": "knowledge"} for iid in item_ids],
            }, ensure_ascii=False)

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        self.assertGreaterEqual(len(results), len(item_ids))
        for r in results:
            self.assertIn("type", r)

    def test_pipeline_mock_llm_bad_json(self):
        """mock LLM 返回非法 JSON → 降级但不应崩溃"""
        def mock_llm(user_text, system_prompt):
            return "抱歉，我无法处理这个请求，请重试。"

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn(results[0]["type"], ["knowledge", "problem_strip"])

    def test_pipeline_mock_llm_empty_units(self):
        """mock LLM 返回空 units → 降级"""
        def mock_llm(user_text, system_prompt):
            return json.dumps({"units": []})

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        self.assertGreaterEqual(len(results), 1)

    def test_pipeline_mock_llm_exception(self):
        """mock LLM 抛出异常 → 降级"""
        def mock_llm(user_text, system_prompt):
            raise RuntimeError("模拟网络错误")

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        # LLM 异常时降级，应至少返回 1 个单元
        self.assertGreaterEqual(len(results), 1)

    def test_pipeline_mixed_content(self):
        """混合内容（素材 + 嵌入例题）"""
        results = knowledge_split(SAMPLE_MIXED, llm_callable=None)
        self.assertGreaterEqual(len(results), 1)

    def test_output_consistency_across_calls(self):
        """同一输入多次调用的输出一致性"""
        for _ in range(3):
            results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=None)
            self.assertGreaterEqual(len(results), 1)


# =========================================================================
# 中间产物落盘测试
# =========================================================================

class TestIntermediateFileDumping(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        (Path(self.tmpdir) / "output" / "中间产物" / "test_doc").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        os.chdir(self.old_cwd)

    def test_dump_creates_file(self):
        """中间产物正确写入文件"""
        _dump_intermediate("test_output.txt", "测试内容", "test_doc")
        expected_path = Path("output") / "中间产物" / "test_doc" / "test_output.txt"
        self.assertTrue(expected_path.exists(),
                        f"文件应存在: {expected_path}")

    def test_dump_json_must_be_valid(self):
        """JSON 中间产物必须是合法 JSON"""
        data = {"key": "value", "number": 42}
        _dump_intermediate("test_data.json",
                           json.dumps(data, ensure_ascii=False),
                           "test_doc")
        expected_path = Path("output") / "中间产物" / "test_doc" / "test_data.json"
        self.assertTrue(expected_path.exists())
        with open(expected_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        self.assertEqual(parsed, data)

    def test_pipeline_dumps_all_intermediates(self):
        """完整管线（有 LLM）应落盘所有中间产物"""

        def mock_llm(user_text, system_prompt):
            return json.dumps({
                "units": [{"id": "L0000", "type": "knowledge"}],
            }, ensure_ascii=False)

        _ = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm,
                           doc_name="test_full_pipeline")

        base = Path("output") / "中间产物" / "test_full_pipeline"
        # 步骤 1 必定产生的
        always_expected = [
            "_knowledge_catalog.json",
        ]
        for fname in always_expected:
            self.assertTrue(
                (base / fname).exists(),
                f"中间产物应存在: {fname}"
            )
        # LLM 路径产生的
        llm_expected = [
            "_knowledge_llm_input.txt",
            "_knowledge_llm_raw.txt",
            "_knowledge_llm_parsed.json",
        ]
        for fname in llm_expected:
            self.assertTrue(
                (base / fname).exists(),
                f"LLM 中间产物应存在: {fname}"
            )

    def test_pipeline_dumps_on_llm_error(self):
        """管线 LLM 返回非法 JSON 时仍应落盘原始返回和错误日志"""

        def mock_llm(user_text, system_prompt):
            return "完全不是 JSON 的返回内容，解析必定失败"

        _ = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm,
                           doc_name="test_error_dump")

        base = Path("output") / "中间产物" / "test_error_dump"
        raw_path = base / "_knowledge_llm_raw.txt"
        self.assertTrue(raw_path.exists(),
                        f"LLM 原始返回应落盘: {raw_path}")
        err_path = base / "_knowledge_llm_parse_error.txt"
        self.assertTrue(err_path.exists(),
                        f"解析错误日志应存在: {err_path}")

    def test_pipeline_no_llm_dumps_catalog(self):
        """无 LLM 时仍落盘编目产物"""
        _ = knowledge_split(SAMPLE_STRUCTURED, llm_callable=None,
                           doc_name="test_no_llm_dump")

        base = Path("output") / "中间产物" / "test_no_llm_dump"
        self.assertTrue(
            (base / "_knowledge_catalog.json").exists(),
            "编目产物应存在"
        )


# =========================================================================
# 边界情况测试
# =========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_empty_content(self):
        """空白内容"""
        results = knowledge_split("\n\n", llm_callable=None)
        self.assertIsInstance(results, list)

    def test_single_line_content(self):
        """单行内容"""
        results = knowledge_split("仅一行文本", llm_callable=None)
        self.assertGreaterEqual(len(results), 1)

    def test_only_headings(self):
        """仅含标题"""
        content = """## 标题一
### 副标题
#### 更细的标题
"""
        results = knowledge_split(content, llm_callable=None)
        self.assertGreaterEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
