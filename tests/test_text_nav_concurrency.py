"""Issue 010：text_nav_tools 并发安全测试

验证全局状态 _current_text 在线程并发下不会互相污染。
"""
import threading

from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool, set_current_text

TEXT_A = """第一段 这是题目A的内容

第二段 包含关键字苹果的内容

第三段 继续题目A的文本"""

TEXT_B = """第一段 这是题目B的内容

第二段 包含关键字香蕉的内容

第三段 继续题目B的文本"""


class TestTextNavConcurrency:
    """验证 text_nav_tools 在并发场景下的正确性。"""

    def _locate_in_thread(self, text: str, keyword: str, results: list, idx: int, barrier: threading.Barrier):
        """在线程中设置文本并执行 locate_paragraph。"""
        set_current_text(text)
        tool = LocateParagraphTool()
        # 等待所有线程就绪，最大化竞态窗口
        barrier.wait()
        result = tool._run(keyword)
        results[idx] = result

    def test_concurrent_locate_no_interference(self):
        """两个线程同时校对不同文本，各自的 locate_paragraph 返回正确结果。"""
        results = [None, None]
        barrier = threading.Barrier(2)

        t_a = threading.Thread(
            target=self._locate_in_thread,
            args=(TEXT_A, "苹果", results, 0, barrier)
        )
        t_b = threading.Thread(
            target=self._locate_in_thread,
            args=(TEXT_B, "香蕉", results, 1, barrier)
        )

        t_a.start()
        t_b.start()
        t_a.join(timeout=5)
        t_b.join(timeout=5)

        # 线程 A 搜索"苹果"，应在 TEXT_A 中找到
        assert results[0] is not None, "线程A未返回结果"
        assert "苹果" in results[0], f"线程A应找到'苹果'，实际: {results[0][:100]}"
        assert "题目A" in results[0], f"线程A应返回题目A内容，实际: {results[0][:100]}"

        # 线程 B 搜索"香蕉"，应在 TEXT_B 中找到
        assert results[1] is not None, "线程B未返回结果"
        assert "香蕉" in results[1], f"线程B应找到'香蕉'，实际: {results[1][:100]}"
        assert "题目B" in results[1], f"线程B应返回题目B内容，实际: {results[1][:100]}"

    def test_concurrent_locate_stress(self):
        """压力测试：10 个线程并发 locate，各自结果不串。"""
        num_threads = 10
        texts = [f"文本{i}号 关键字第{i}组 唯一标记_{i}" for i in range(num_threads)]
        keywords = [f"关键字第{i}组" for i in range(num_threads)]
        results = [None] * num_threads
        barrier = threading.Barrier(num_threads)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(
                target=self._locate_in_thread,
                args=(texts[i], keywords[i], results, i, barrier)
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for i in range(num_threads):
            assert results[i] is not None, f"线程{i}未返回结果"
            assert keywords[i] in results[i], f"线程{i}应找到'{keywords[i]}'，实际: {results[i][:100]}"
            assert f"唯一标记_{i}" in results[i], f"线程{i}应包含唯一标记_{i}，实际: {results[i][:100]}"

    def test_read_section_thread_safety(self):
        """read_section 在并发下返回各自文本的正确段落。"""
        result_a = [None]
        result_b = [None]
        barrier = threading.Barrier(2)

        def _read_a():
            set_current_text(TEXT_A)
            tool = ReadSectionTool()
            barrier.wait()
            result_a[0] = tool._run(2, 2)

        def _read_b():
            set_current_text(TEXT_B)
            tool = ReadSectionTool()
            barrier.wait()
            result_b[0] = tool._run(2, 2)

        t_a = threading.Thread(target=_read_a)
        t_b = threading.Thread(target=_read_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=5)
        t_b.join(timeout=5)

        assert "苹果" in result_a[0], f"线程A read_section 应包含'苹果'，实际: {result_a[0]}"
        assert "香蕉" in result_b[0], f"线程B read_section 应包含'香蕉'，实际: {result_b[0]}"

    def test_set_and_get_in_same_thread(self):
        """同一线程内 set → locate 正常工作。"""
        set_current_text(TEXT_A)
        tool = LocateParagraphTool()
        result = tool._run("苹果")
        assert "苹果" in result
        assert "题目A" in result

    def test_no_text_returns_error(self):
        """未设置文本时工具返回错误提示。"""
        # 在新线程中测试，确保不受其他测试的文本污染
        result = [None]

        def _run():
            tool = LocateParagraphTool()
            result[0] = tool._run("anything")

        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=5)
        assert "[error: no text]" in result[0]
