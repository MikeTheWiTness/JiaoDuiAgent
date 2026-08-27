"""测试 sympy 沙箱子进程超时即终止（P1-4）。

回归：修复前 subprocess.run/call 在 timeout 抛 TimeoutExpired 但不终止子进程，
导致 sympy 超时后残留进程持续占用 CPU。修复后超时即 kill。
（pdf_compiler 的 _run_with_timeout 已随 LaTeX/PDF 排版下线删除，ADR-0030）
"""
from shared.sympy_tools.sandbox import execute_code


class TestSympySandboxTimeout:
    """sympy 沙箱子进程超时即终止。"""

    def test_execute_code_timeout_returns_error(self):
        result = execute_code("import time; time.sleep(30); print('{}')", timeout=1)
        assert result["success"] is False
        assert "timed out" in result["error"]