"""测试 BashTool 安全加固：命令白名单 + 危险模式拦截 + 路径限制。"""
import pytest

from shared.bash_tool import _validate_bash_command


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
        err = _validate_bash_command("cat /etc/passwd", "/tmp/work")
        assert err is not None

    def test_block_cd_command(self):
        err = _validate_bash_command("cd / && ls", "/tmp/work")
        assert err is not None

    def test_allow_path_inside_allowed_dir(self):
        err = _validate_bash_command("cat /tmp/work/file.txt", "/tmp/work")
        assert err is None

    # ---- 未知命令 ----

    def test_block_unknown_command(self):
        err = _validate_bash_command("nmap localhost", None)
        assert err is not None
