"""测试子进程超时终止（P1-4）。

回归：修复前 subprocess.run/call 在 timeout 抛 TimeoutExpired 但不终止子进程，
导致 xelatex/sympy 超时后残留进程持续占用 CPU 并可能写出半成品。修复后超时即 kill。
"""
import subprocess
import sys

import pytest

from shared.pdf_compiler import _run_with_timeout
from shared.sympy_tools.sandbox import execute_code


class TestRunWithTimeout:
    """pdf_compiler._run_with_timeout 的行为契约。"""

    def test_normal_completion_returns_returncode(self):
        cmd = [sys.executable, "-c", "print('ok')"]
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        assert _run_with_timeout(cmd, kw, "测试阶段") == 0

    def test_nonzero_returncode_propagated(self):
        cmd = [sys.executable, "-c", "import sys; sys.exit(3)"]
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        assert _run_with_timeout(cmd, kw, "测试阶段") == 3

    def test_timeout_raises_runtime_error(self):
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "timeout": 1}
        with pytest.raises(RuntimeError, match="超时"):
            _run_with_timeout(cmd, kw, "测试阶段")


class TestSympySandboxTimeout:
    """sympy 沙箱子进程超时即终止。"""

    def test_execute_code_timeout_returns_error(self):
        result = execute_code("import time; time.sleep(30); print('{}')", timeout=1)
        assert result["success"] is False
        assert "timed out" in result["error"]
