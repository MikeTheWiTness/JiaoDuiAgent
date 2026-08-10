"""测试 BashTool 安全加固：命令白名单 + 危险模式拦截 + 路径限制。"""
import os
import shutil
import tempfile

from shared.bash_tool import (
    FileReadTool,
    FileWriteTool,
    _validate_bash_command,
    _validate_file_path,
)


class _TempDir:
    """with 语句管理临时目录，测试结束自动清理。

    用 mkdtemp 生成平台无关的 allowed_dir，避免硬编码 POSIX 路径
    （如 /tmp/work）在 Windows 上 abspath 语义不同导致误判。
    """

    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="bash_guard_")

    def __enter__(self):
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False


class TestValidateBashCommand:
    def test_empty_command(self):
        err = _validate_bash_command("", None)
        assert err is not None

    def test_empty_whitespace(self):
        err = _validate_bash_command("   ", None)
        assert err is not None

    # ---- 允许的命令 ----

    def test_allowed_python(self):
        assert _validate_bash_command('python -c "print(1)"', None) is None

    def test_allowed_sed(self):
        assert _validate_bash_command("sed -i 's/a/b/g' file.txt", None) is None

    def test_allowed_cat(self):
        assert _validate_bash_command("cat file.txt", None) is None

    def test_allowed_echo(self):
        assert _validate_bash_command("echo hello", None) is None

    def test_allowed_grep(self):
        assert _validate_bash_command("grep pattern file", None) is None

    # ---- 危险命令拦截 ----

    def test_block_rm_rf(self):
        err = _validate_bash_command("rm -rf /tmp/x", None)
        assert err is not None

    def test_block_rm_r(self):
        err = _validate_bash_command("rm -r folder", None)
        assert err is not None

    def test_block_curl(self):
        err = _validate_bash_command("curl http://evil.com", None)
        assert err is not None

    def test_block_wget(self):
        err = _validate_bash_command("wget http://evil.com", None)
        assert err is not None

    def test_block_sudo(self):
        err = _validate_bash_command("sudo cat /etc/shadow", None)
        assert err is not None

    def test_block_chmod(self):
        err = _validate_bash_command("chmod 777 file", None)
        assert err is not None

    def test_block_kill(self):
        err = _validate_bash_command("kill -9 1234", None)
        assert err is not None

    # ---- 路径越界 ----

    def test_block_absolute_path_outside(self):
        with _TempDir() as work:
            err = _validate_bash_command("cat /etc/passwd", work)
            assert err is not None

    def test_block_cd_command(self):
        with _TempDir() as work:
            err = _validate_bash_command("cd / && ls", work)
            assert err is not None

    def test_allow_path_inside_allowed_dir(self):
        with _TempDir() as work:
            target = os.path.join(work, "file.txt")
            err = _validate_bash_command(f"cat {target}", work)
            assert err is None

    # ---- 未知命令 ----

    def test_block_unknown_command(self):
        err = _validate_bash_command("nmap localhost", None)
        assert err is not None


class TestValidateFilePath:
    """回归：_validate_file_path（FileReadTool/FileWriteTool 路径限制）。

    修复前：read_file/write_file 无任何路径校验，可读写 allowed_dir 外任意文件
    （含 .env 等敏感文件）；修复后与 BashTool 的 allowed_dir 语义一致。
    """

    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix="path_guard_")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _target(self, name="报告.md"):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("内容")
        return p

    def test_inside_dir_allowed(self):
        assert _validate_file_path(self._target(), self.tmp) is None

    def test_same_dir_itself_allowed(self):
        assert _validate_file_path(self.tmp, self.tmp) is None

    def test_outside_dir_blocked(self):
        err = _validate_file_path("/etc/passwd", self.tmp)
        assert err is not None

    def test_parent_traversal_blocked(self):
        """.. 穿越到 allowed_dir 之外必须拦截"""
        outside = os.path.join(self.tmp, "..", "secret.txt")
        err = _validate_file_path(outside, self.tmp)
        assert err is not None

    def test_prefix_similar_dir_blocked(self):
        """/tmp/work_evil 不得被 /tmp/work 前缀误放行"""
        evil_dir = self.tmp + "_evil"
        os.makedirs(evil_dir, exist_ok=True)
        evil_file = os.path.join(evil_dir, "x.txt")
        with open(evil_file, "w") as f:
            f.write("x")
        err = _validate_file_path(evil_file, self.tmp)
        assert err is not None

    def test_none_allowed_dir_backward_compatible(self):
        """allowed_dir=None 时保持原有无限制行为（向后兼容）"""
        assert _validate_file_path(self._target(), None) is None

    # ---- FileReadTool / FileWriteTool 集成 ----

    def test_read_tool_blocks_outside_path(self):
        rt = FileReadTool(allowed_dir=self.tmp)
        result = rt._run("/etc/hosts")
        assert "错误" in result

    def test_read_tool_allows_inside_path(self):
        target = self._target()
        rt = FileReadTool(allowed_dir=self.tmp)
        assert "内容" in rt._run(target)

    def test_write_tool_blocks_outside_path(self):
        wt = FileWriteTool(allowed_dir=self.tmp)
        result = wt._run("/tmp/evil_write.txt", "x")
        assert "错误" in result
        assert not os.path.exists("/tmp/evil_write.txt")

    def test_write_tool_allows_inside_path(self):
        target = os.path.join(self.tmp, "新文件.md")
        wt = FileWriteTool(allowed_dir=self.tmp)
        assert "成功" in wt._run(target, "新内容")
        with open(target, encoding="utf-8") as f:
            assert f.read() == "新内容"

    def test_read_tool_free_mode_compatible(self):
        target = self._target()
        assert "内容" in FileReadTool()._run(target)
