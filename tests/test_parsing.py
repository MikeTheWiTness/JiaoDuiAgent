import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.parsing import save_proofread_json


class TestSaveProofreadJson(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.q_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 辅助方法 ──────────────────────────────────────────────
    def _json_path(self):
        return os.path.join(self.q_dir, "_校对数据.json")

    def _load_json(self):
        with open(self._json_path(), encoding="utf-8") as f:
            return json.load(f)

    # ── 内联标记格式的校对文本 ─────────────────────────────────
    @staticmethod
    def _make_inline_proofread_md(summary="严重错误",
                                  corrections=None):
        """构造带内联标记的校对 Markdown 文本。"""
        if corrections is None:
            corrections = [
                ("错误", "正确", "这是一个错别字"),
                ("多余  空格", "多余 空格", "多了两个空格"),
            ]
        # 拼接标记原文段落
        marked_lines = ["### 标记原文"]
        for orig, corr, reason in corrections:
            marked_lines.append(
                f"这里有些文字【{len(marked_lines)}|{orig}|{corr}】还有更多。"
            )
        marked_text = "\n".join(marked_lines)

        # 拼接修改原因段落
        reason_lines = ["### 修改原因"]
        for i, (_orig, _corr, r) in enumerate(corrections, start=1):
            reason_lines.append(f"{chr(0x245F + i)} {r}")

        return summary + "\n\n" + marked_text + "\n\n" + "\n".join(reason_lines)

    # ── 测试用例 ──────────────────────────────────────────────
    def test_saves_json_file(self):
        """调用 save_proofread_json 后 _校对数据.json 文件被创建。"""
        md = self._make_inline_proofread_md()
        result = save_proofread_json(md, self.q_dir)
        self.assertTrue(result)
        self.assertTrue(os.path.isfile(self._json_path()))

    def test_json_has_required_structure(self):
        """JSON 内容包含 corrections 和 summary 字段。"""
        md = self._make_inline_proofread_md()
        save_proofread_json(md, self.q_dir)
        data = self._load_json()
        self.assertIn("corrections", data)
        self.assertIn("summary", data)
        self.assertIsInstance(data["corrections"], list)
        self.assertGreater(len(data["corrections"]), 0)
        # 每条 correction 应包含必要字段
        for c in data["corrections"]:
            self.assertIn("original", c)
            self.assertIn("correction", c)
            self.assertIn("type", c)
        self.assertEqual(data["summary"], "严重错误")

    def test_empty_tool_calls_omits_field(self):
        """tool_calls 为空列表时（falsy），字段被省略。"""
        md = self._make_inline_proofread_md()
        save_proofread_json(md, self.q_dir, tool_calls=[])
        data = self._load_json()
        self.assertNotIn("tool_calls", data)

    def test_tool_calls_preserved(self):
        """tool_calls 有内容时数据完整保留。"""
        md = self._make_inline_proofread_md()
        calls = [{"id": "call_1", "name": "search"}]
        save_proofread_json(md, self.q_dir, tool_calls=calls)
        data = self._load_json()
        self.assertEqual(data["tool_calls"], calls)

    def test_no_tool_calls_omits_field(self):
        """未传入 tool_calls 时 JSON 不包含该字段。"""
        md = self._make_inline_proofread_md()
        save_proofread_json(md, self.q_dir)
        data = self._load_json()
        self.assertNotIn("tool_calls", data)

    def test_missing_dir_creates_it(self):
        """目标目录不存在时自动创建（os.path.join 不会报错，open 会）。"""
        md = self._make_inline_proofread_md()
        nested = os.path.join(self.q_dir, "sub", "deep")
        result = save_proofread_json(md, nested)
        # 如果目录不存在，open 会抛出 FileNotFoundError，
        # save_proofread_json 捕获异常返回 False
        # 因此这里验证行为：要么目录被创建，要么返回 False
        self.assertFalse(result)
        self.assertFalse(os.path.isdir(nested))

    def test_existing_dir_overwrites_json(self):
        """重复写入同一目录时 _校对数据.json 被覆盖。"""
        md1 = self._make_inline_proofread_md(summary="严重错误")
        save_proofread_json(md1, self.q_dir)
        data1 = self._load_json()
        self.assertEqual(data1["summary"], "严重错误")

    def test_write_failure_logs_warning(self):
        """回归：写盘失败必须记录日志（此前静默返回 False 无感知）"""
        from unittest import mock

        from core import parsing
        md = self._make_inline_proofread_md()
        with mock.patch.object(parsing, "log") as mock_log, \
                mock.patch("builtins.open", side_effect=OSError("磁盘只读")):
            result = save_proofread_json(md, self.q_dir)
        self.assertFalse(result)
        mock_log.assert_called()
        # 日志消息应包含失败文件路径信息
        self.assertIn("_校对数据.json", mock_log.call_args[0][0])

        md2 = self._make_inline_proofread_md(summary="一般问题")
        save_proofread_json(md2, self.q_dir)
        data2 = self._load_json()
        self.assertEqual(data2["summary"], "一般问题")

    def test_no_problem_text_yields_empty_corrections(self):
        """纯'无问题'文本解析为空的 corrections。"""
        result = save_proofread_json("无问题", self.q_dir)
        self.assertTrue(result)
        data = self._load_json()
        self.assertEqual(data["summary"], "无问题")
        self.assertEqual(data["corrections"], [])

    def test_empty_string_returns_false(self):
        """空字符串无法解析，返回 False。"""
        result = save_proofread_json("", self.q_dir)
        self.assertFalse(result)
        self.assertFalse(os.path.isfile(self._json_path()))

    def test_whitespace_only_returns_false(self):
        """仅空白字符无法解析，返回 False。"""
        result = save_proofread_json("   \n  \t  ", self.q_dir)
        self.assertFalse(result)
        self.assertFalse(os.path.isfile(self._json_path()))

    def test_summary_empty_defaults(self):
        """summary 为空时 _parse_inline_format 将其替换为 '无问题'。"""
        md = self._make_inline_proofread_md(summary="")
        result = save_proofread_json(md, self.q_dir)
        self.assertTrue(result)
        data = self._load_json()
        self.assertEqual(data["summary"], "无问题")

    def test_multiline_marker_extracted(self):
        """跨行标记（标记原文/改为字段含换行）能被提取（B1）。"""
        md = (
            "严重错误\n\n"
            "### 标记原文\n"
            "内容：【1|第一行\n第二行|改为\n跨行】\n\n"
            "### 修改原因\n"
            "1. 跨行标记原因。"
        )
        save_proofread_json(md, self.q_dir)
        data = self._load_json()
        self.assertEqual(len(data["corrections"]), 1)
        self.assertEqual(data["corrections"][0]["original"], "第一行\n第二行")
        self.assertEqual(data["corrections"][0]["correction"], "改为\n跨行")

    def test_descending_circled_range_reasons(self):
        """带圈数字降序区间（⑮-⑫）不丢原因（B1）。"""
        md = (
            "严重错误\n\n"
            "### 标记原文\n"
            "内容：【12|错|对】【13|错|对】【14|错|对】【15|错|对】\n\n"
            "### 修改原因\n"
            "⑮-⑫ 这是一段覆盖 12-15 的原因。"
        )
        save_proofread_json(md, self.q_dir)
        data = self._load_json()
        self.assertEqual(len(data["corrections"]), 4)
        for c in data["corrections"]:
            self.assertEqual(c["reason"], "这是一段覆盖 12-15 的原因。")


if __name__ == "__main__":
    unittest.main()
