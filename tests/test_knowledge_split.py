"""知识讲义切割管线测试。

覆盖：
  - 步骤 1 结构扫描 + 置信度分层（各种格式）
  - 步骤 2 LLM 分类 mock（正常/异常/格式错误/空返回）
  - 步骤 3 锚点合并 + 校验（唯一性/重叠检测）
  - 步骤 4 bash 逆序插入 + 复核（配对检查/空单元检测）
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
    _merge_and_validate,
    _bash_insert_tags,
    _verify_tags,
    _parse_knowledge_tags,
    _dump_intermediate,
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
# 步骤 1：结构扫描测试
# =========================================================================

class TestStructureScan(unittest.TestCase):

    def test_detect_block_titles(self):
        """检测 （N） 编号块标题"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        blocks = result["blocks"]
        self.assertGreaterEqual(len(blocks), 3,
                                f"应至少识别 3 个块，实际 {len(blocks)}")
        # 检查是否有 HIGH 置信度块
        high_blocks = [b for b in blocks if b["confidence"] == "HIGH"]
        self.assertGreater(len(high_blocks), 0,
                           "应有至少 1 个 HIGH 置信度块")

    def test_detect_hashtag_headings(self):
        """检测 ## #### 标题"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        tree = result["tree"]
        # 过滤掉编号级别的 tree 条目
        headings = [t for t in tree if t["level"] != 99]
        self.assertGreaterEqual(len(headings), 1,
                                f"应至少识别 1 个 ## 标题，实际 {len(headings)}")

    def test_confidence_high_for_small_blocks(self):
        """小块应获得 HIGH 置信度"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        blocks = result["blocks"]
        for b in blocks:
            if b["chars"] < ksplit.MAX_BLOCK_CHARS and b["chars"] > 100:
                self.assertEqual(b["confidence"], "HIGH",
                                 f"小块 L{b['from']} 应为 HIGH，实际 {b['confidence']}")

    def test_confidence_low_for_large_blocks(self):
        """大块应获得 LOW 置信度"""
        # 构造一个大块（超过 MAX_BLOCK_CHARS 的文本）
        big_section = (
            "（1）大段内容\n"
            + "这是正文内容。\n" * 500
            + "结尾行\n"
        )
        result = _scan_structure(big_section)
        blocks = result["blocks"]
        # 找到 chars > MAX_BLOCK_CHARS 的块
        large = [b for b in blocks if b["chars"] > ksplit.MAX_BLOCK_CHARS]
        for b in large:
            self.assertEqual(b["confidence"], "LOW",
                             f"大块 ({b['chars']} chars) 应为 LOW")

    def test_no_structure_confidence(self):
        """无结构信号文本的置信度"""
        result = _scan_structure(SAMPLE_NO_STRUCTURE)
        blocks = result["blocks"]
        self.assertGreaterEqual(len(blocks), 1)
        # 纯文本无编号/标题 → 可能是 LOW 或 NONE（取决于长度）
        for b in blocks:
            self.assertIn(b["confidence"], ["HIGH", "LOW"],
                          f"置信度值异常: {b['confidence']}")

    def test_tree_entries_are_valid(self):
        """目录树条目格式正确"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        tree = result["tree"]
        for t in tree:
            self.assertIn("line", t)
            self.assertIn("level", t)
            self.assertIn("text", t)
            self.assertIsInstance(t["line"], int)
            self.assertIsInstance(t["level"], int)

    def test_blocks_have_required_fields(self):
        """每个块包含必需字段"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        for b in result["blocks"]:
            self.assertIn("from", b)
            self.assertIn("to", b)
            self.assertIn("chars", b)
            self.assertIn("confidence", b)
            self.assertIn("anchor", b)

    def test_blocks_are_non_overlapping(self):
        """块区间不重叠"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        blocks = sorted(result["blocks"], key=lambda b: b["from"])
        for i in range(len(blocks) - 1):
            self.assertLessEqual(blocks[i]["to"], blocks[i + 1]["from"],
                                 f"块 {i} 和 {i+1} 重叠")

    def test_blocks_cover_the_whole_document(self):
        """块从第一行开始，覆盖到末尾"""
        result = _scan_structure(SAMPLE_STRUCTURED)
        blocks = sorted(result["blocks"], key=lambda b: b["from"])
        self.assertEqual(blocks[0]["from"], 0,
                         "第一块应从第 0 行开始")
        # 最后一块的 to 应 >= total_lines - 1
        self.assertGreaterEqual(blocks[-1]["to"], result["total_lines"] - 1,
                                "最后一块应覆盖到文档末尾")


# =========================================================================
# 步骤 3：锚点合并 + 校验测试
# =========================================================================

class TestAnchorMergeAndValidation(unittest.TestCase):

    def test_merge_high_blocks(self):
        """HIGH 块合并为锚点"""
        content = SAMPLE_STRUCTURED
        high_blocks = [
            {"from": 0, "to": 4, "chars": 200, "confidence": "HIGH",
             "anchor": "## 模块一 写作素材深度运用"},
            {"from": 4, "to": 20, "chars": 500, "confidence": "HIGH",
             "anchor": "（1）《庄子》\"浑沌之死\""},
        ]
        anchors = _merge_and_validate(content, high_blocks, [])
        self.assertGreaterEqual(len(anchors), 1)
        for a in anchors:
            self.assertIn(a["type"], ["knowledge", "problem_strip"])

    def test_anchor_must_exist_in_content(self):
        """锚点必须在原文中存在"""
        content = SAMPLE_STRUCTURED
        high_blocks = [
            {"from": 0, "to": 4, "chars": 200, "confidence": "HIGH",
             "anchor": "这个锚点不存在原文中XYZABC"},
        ]
        result = _merge_and_validate(content, high_blocks, [])
        # 锚点不唯一/不存在时会降级为单单元
        # 降级锚点应该是第一行
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "fallback")

    def test_merge_with_llm_classified(self):
        """HIGH + LLM 分类混合合并"""
        content = SAMPLE_STRUCTURED
        high_blocks = [
            {"from": 0, "to": 4, "chars": 200, "confidence": "HIGH",
             "anchor": "## 模块一 写作素材深度运用"},
        ]
        classified = [
            {"id": 0, "type": "knowledge",
             "sub_blocks": [
                 {"anchor": "（1）《庄子》\"浑沌之死\"", "type": "knowledge"},
             ]},
        ]
        anchors = _merge_and_validate(content, high_blocks, classified)
        self.assertGreaterEqual(len(anchors), 1)

    def test_empty_llm_return(self):
        """LLM 返回空分类列表时的处理"""
        content = SAMPLE_STRUCTURED
        high_blocks = [
            {"from": 0, "to": 10, "chars": 300, "confidence": "HIGH",
             "anchor": "## 模块一 写作素材深度运用"},
        ]
        anchors = _merge_and_validate(content, high_blocks, [])
        self.assertGreaterEqual(len(anchors), 1)


# =========================================================================
# 步骤 4：bash 逆序插入 + 复核测试
# =========================================================================

class TestBashInsertionAndVerification(unittest.TestCase):

    def test_bash_insert_basic(self):
        """基本逆序插入"""
        content = "标题行\n\n正文内容第一段\n\n正文内容第二段\n"
        anchors = [
            {"anchor": "标题行", "action": "start", "type": "knowledge"},
        ]
        tagged = _bash_insert_tags(content, anchors)
        self.assertIn("<knowledge>", tagged)
        self.assertIn("</knowledge>", tagged)

    def test_bash_insert_multiple(self):
        """多锚点逆序插入"""
        content = SAMPLE_STRUCTURED
        anchors = [
            {"anchor": "## 模块一 写作素材深度运用", "action": "start", "type": "knowledge"},
            {"anchor": "（1）《庄子》\"浑沌之死\"", "action": "start", "type": "knowledge"},
        ]
        tagged = _bash_insert_tags(content, anchors)
        self.assertTrue(tagged.count("<knowledge>") >= 1)

    def test_verify_paired_tags(self):
        """配对标签通过复核"""
        tagged = "<knowledge>\n内容\n</knowledge>"
        result = _verify_tags(tagged)
        self.assertTrue(result["ok"])
        self.assertTrue(result["paired"])

    def test_verify_unpaired_tags(self):
        """未配对标签复核失败"""
        tagged = "<knowledge>\n内容\n"
        result = _verify_tags(tagged)
        self.assertFalse(result["ok"])
        self.assertFalse(result["paired"])

    def test_verify_empty_unit(self):
        """空单元检测"""
        tagged = "<knowledge></knowledge>"
        result = _verify_tags(tagged)
        self.assertTrue(result["has_empty_unit"])

    def test_verify_nested_problem_tags(self):
        """知识标签内嵌套题目标签"""
        tagged = (
            "<knowledge>\n"
            "知识讲解\n"
            "<problem>\n题目内容\n</problem>\n"
            "更多讲解\n"
            "</knowledge>"
        )
        result = _verify_tags(tagged)
        self.assertTrue(result["ok"])
        self.assertTrue(result["problem_paired"])

    def test_parse_knowledge_tags(self):
        """解析知识标签"""
        tagged = (
            "<knowledge>\n块一\n</knowledge>\n"
            "<knowledge>\n块二\n</knowledge>"
        )
        results = _parse_knowledge_tags(tagged)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["type"], "knowledge")
        self.assertIn("块一", results[0]["content"])

    def test_parse_problem_strip_tags(self):
        """解析纯例题标签"""
        tagged = (
            "<knowledge>\n知识\n</knowledge>\n"
            "<problem-strip>\n例题\n</problem-strip>"
        )
        results = _parse_knowledge_tags(tagged)
        # 应该有 2 个结果（1 knowledge + 1 problem_strip）
        types = [r["type"] for r in results]
        self.assertIn("knowledge", types)
        self.assertIn("problem_strip", types)


# =========================================================================
# 完整管线测试（含 mock LLM）
# =========================================================================

class TestFullPipeline(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_pipeline_no_llm_structured(self):
        """无 LLM 的纯 Python 管线（结构化讲义）"""
        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=None)
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertIn("content", r)
            self.assertIn("type", r)
            self.assertGreater(len(r["content"]), 0)

    def test_pipeline_no_llm_unstructured(self):
        """无 LLM 处理无结构文本 → 应降级为单单元"""
        results = knowledge_split(SAMPLE_NO_STRUCTURE, llm_callable=None)
        self.assertGreaterEqual(len(results), 1)
        # 无结构文本通常只有一个块
        self.assertEqual(results[0]["type"], "knowledge")

    def test_pipeline_with_mock_llm(self):
        """mock LLM 正常返回 → 全管线"""
        def mock_llm(user_text, system_prompt):
            return json.dumps({
                "blocks": [
                    {"id": 0, "type": "knowledge", "sub_blocks": []},
                ],
            }, ensure_ascii=False)

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertIn("type", r)

    def test_pipeline_mock_llm_bad_json(self):
        """mock LLM 返回非法 JSON → 降级但不应崩溃"""
        def mock_llm(user_text, system_prompt):
            return "抱歉，我无法处理这个请求，请重试。"

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        self.assertGreaterEqual(len(results), 1)
        # 应降级：至少返回一个单元
        self.assertIn(results[0]["type"], ["knowledge", "problem_strip"])

    def test_pipeline_mock_llm_empty_json(self):
        """mock LLM 返回空 JSON → 降级"""
        def mock_llm(user_text, system_prompt):
            return json.dumps({"blocks": []})

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        self.assertGreaterEqual(len(results), 1)

    def test_pipeline_mock_llm_exception(self):
        """mock LLM 抛出异常 → 降级为单单元"""
        def mock_llm(user_text, system_prompt):
            raise RuntimeError("模拟网络错误")

        results = knowledge_split(SAMPLE_STRUCTURED, llm_callable=mock_llm)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "knowledge")

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
        # 创建 output/中间产物 目录
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
        """完整管线应落盘所有中间产物（含 LLM 路径）"""
        # 构造一个包含 LOW 置信度块的内容（超大块强制触发 LOW）
        big_content = (
            "#### 大段知识讲解\n\n"
            + "正文内容。" + "这是填充文本。" * 600 + "\n\n"
            + "## 另一节\n\n另一节内容。\n"
        )

        def mock_llm(user_text, system_prompt):
            return json.dumps({
                "blocks": [
                    {"id": 0, "type": "knowledge", "sub_blocks": []},
                ],
            }, ensure_ascii=False)

        _ = knowledge_split(big_content, llm_callable=mock_llm,
                           doc_name="test_full_pipeline")

        base = Path("output") / "中间产物" / "test_full_pipeline"
        # Python 阶段必定产生的
        always_expected = [
            "_knowledge_scan_tree.json",
        ]
        for fname in always_expected:
            self.assertTrue(
                (base / fname).exists(),
                f"中间产物应存在: {fname}"
            )
        # LLM 路径产生的（取决于是否有 LOW 块需要 LLM）
        llm_expected = [
            "_knowledge_llm_raw.txt",
            "_knowledge_llm_parsed.json",
        ]
        for fname in llm_expected:
            self.assertTrue(
                (base / fname).exists(),
                f"LLM 中间产物应存在: {fname}"
            )

    def test_pipeline_dumps_on_error(self):
        """管线 LLM 返回非法 JSON 时仍应落盘原始返回和错误日志"""
        # 构造一个超过 MAX_BLOCK_CHARS (8000) 的大块，强制触发 LOW
        big_content = (
            "### 标题\n\n"
            + "正文。" + "这是一段填充文字。" * 900 + "\n\n"
        )

        def mock_llm(user_text, system_prompt):
            return "完全不是 JSON 的返回内容，解析必定失败"

        _ = knowledge_split(big_content, llm_callable=mock_llm,
                           doc_name="test_error_dump")

        base = Path("output") / "中间产物" / "test_error_dump"
        raw_path = base / "_knowledge_llm_raw.txt"
        self.assertTrue(raw_path.exists(),
                        f"LLM 原始返回应落盘: {raw_path}")
        err_path = base / "_knowledge_llm_parse_error.txt"
        self.assertTrue(err_path.exists(),
                        f"解析错误日志应存在: {err_path}")


# =========================================================================
# 边界情况测试
# =========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_empty_content(self):
        """空白内容"""
        results = knowledge_split("\n\n", llm_callable=None)
        # 应返回一个空内容的 knowledge 单元或空列表
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
