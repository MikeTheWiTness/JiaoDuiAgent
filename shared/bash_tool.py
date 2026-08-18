"""BashTool + FileReadTool + FileWriteTool —— 让 LLM 直接操作文件。

用于格式修正等场景：LLM 不再返回修正后的文本（可能格式再出错），
而是直接编辑目标文件，编辑后由 Python 端重读验证。
"""
import os
import re
import shlex
import subprocess

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from shared.sympy_tools.safety import check_dangerous

# ─── BashTool ───────────────────────────────────────────────

BASH_TIMEOUT = 30  # Bash 命令执行超时（秒）

# 危险命令模式（阻止 LLM 执行）
_DANGEROUS_PATTERNS = [
    r'\brm\s+-rf?\b',            # rm -rf / rm -r
    r'\bcurl\b',                  # 数据外传
    r'\bwget\b',                  # 数据外传
    r'\bnc\b',                    # netcat
    r'\bsudo\b',                  # 提权
    r'>\s*/dev/',                 # 写入设备文件
    r'\bchmod\b',                 # 权限修改
    r'\bchown\b',                 # 所有者修改
    r'\bkill\b',                  # 进程终止
    r'\breboot\b',                # 系统重启
    r'\bshutdown\b',              # 关机
    r'\bmkfs\.',                  # 格式化
    r'\bdd\s+if=',                # 磁盘操作
]

# 允许的命令（仅这些命令可通过 BashTool 执行）
_ALLOWED_COMMANDS = [
    "python", "python3",
    "sed", "cat", "type", "dir", "ls",
    "echo", "grep", "find", "head", "tail",
    "wc", "sort", "uniq", "tr", "cut",
    "mkdir", "cp", "mv",
]

_WINDOWS_ABSOLUTE_RE = re.compile(r'^[A-Za-z]:[\\/]')


def _contains_shell_metachar(command: str) -> bool:
    """检查命令中是否有可执行 shell 多命令/注入的元字符。

    单引号内的字符安全；双引号内的 $ 和反引号仍会被 shell 展开，
    因此视为危险。反斜杠仅用于跳过下一个字符的判断。
    """
    in_single = False
    in_double = False
    escaped = False
    for ch in command:
        if escaped:
            escaped = False
            continue
        if ch == "\\" and not in_single:
            escaped = True
            continue
        if in_single:
            if ch == "'":
                in_single = False
            continue
        if in_double:
            if ch == '"':
                in_double = False
            elif ch in "$`":
                return True
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch in ';|&<>()`${}\n\r':
            return True
    return False


def _is_outside_allowed_dir(token: str, allowed_real: str) -> bool:
    """判断 token 作为路径是否落在 allowed_real 之外。

    相对路径以 allowed_real 为基准求 realpath，可同时拦截
    `..` 穿越、绝对路径和目录内符号链接指向外部的情况。
    """
    if not token or token.startswith("-"):
        return False
    if token.startswith("~") or _WINDOWS_ABSOLUTE_RE.match(token) or os.path.isabs(token):
        target = os.path.realpath(token)
    else:
        target = os.path.realpath(os.path.join(allowed_real, token))
    return not (target == allowed_real or target.startswith(allowed_real + os.sep))


def _validate_bash_command(command: str, allowed_dir: str | None) -> str | None:
    """验证 bash 命令安全性。返回错误消息，通过返回 None。

    检查：
    1. 命令非空
    2. 不含 shell 多命令/注入元字符（; | & < > $() `、换行等）
    3. 不含危险模式（rm -rf / curl / wget 等）
    4. 仅使用允许的命令；python 仅允许 `python -c "<代码>"`
    5. 如有 allowed_dir，所有参数路径必须落在 allowed_dir 内
    """
    stripped = command.strip()
    if not stripped:
        return "错误：命令不能为空"

    # 0. 拒绝 shell 多命令/注入形态（管道、分号、&&、换行、命令替换、重定向等）
    if _contains_shell_metachar(stripped):
        return (
            "错误：命令包含不支持的 shell 元字符（管道/分号/重定向/命令替换/换行等）；"
            "BashTool 仅允许单条简单命令"
        )

    # 1. 危险模式检查
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, stripped):
            return f"错误：命令包含禁止的模式（{pat}）"

    # 2. 白名单与参数解析
    try:
        args = shlex.split(stripped, posix=(os.name != "nt"))
    except ValueError as e:
        return f"错误：命令无法解析（引号不匹配等）：{e}"
    if not args:
        return "错误：命令不能为空"

    first_cmd = args[0].lower()
    if first_cmd not in _ALLOWED_COMMANDS:
        return f"错误：不允许的命令 '{first_cmd}'。允许的命令: {', '.join(_ALLOWED_COMMANDS[:6])}..."

    # 2.5 python 仅允许 `python -c "<代码>"` 的纯计算形态；
    # python -m / 脚本路径 / 复杂参数会绕过 -c 代码扫描，一律拒绝。
    if first_cmd in ("python", "python3"):
        if len(args) != 3 or args[1] != "-c":
            return "错误：python 仅允许 python -c '<代码>' 单条命令（禁止 -m/脚本路径）"
        danger = check_dangerous(args[2])
        if danger:
            return f"错误：python -c 代码包含危险操作（{danger}）"

    # 3. 路径越界检查（如有 allowed_dir）
    if allowed_dir:
        allowed = os.path.realpath(os.path.abspath(allowed_dir))
        python_code = args[2] if first_cmd in ("python", "python3") and len(args) >= 3 else None
        for token in args:
            if token == python_code:
                continue
            if _is_outside_allowed_dir(token, allowed):
                return f"错误：禁止访问 allowed_dir 外的路径: {token}"

    return None


class BashParams(BaseModel):
    command: str = Field(
        description="要执行的单条 bash 命令。不支持管道、重定向、命令替换等 shell 特性。"
        "文件读写请用 read_file/write_file/edit_file 专用工具。"
    )


class BashTool(BaseTool):
    """让 LLM 执行 bash 命令来直接操作文件。

    用途：格式修正时，LLM 用 cat/type 读取文件内容，用 sed / python -c 等
    直接修改文件，Python 端在工具返回后重读文件进行验证。

    安全约束：命令白名单 + 危险模式拦截 + allowed_dir 路径限制。
    """

    name: str = "bash"
    description: str = (
        "执行单条 bash 命令来读取或编辑文件。常用命令：\n"
        "- sed -i 's/旧/新/g' <文件路径> — 替换文本\n"
        "- cat <文件路径> — 读取文件（Windows 不支持，用 read_file）\n"
        "注意：仅支持单条简单命令，不支持管道/分号/重定向/命令替换/换行等 shell 特性；"
        "优先用 read_file/write_file/edit_file 专用工具读写文件（受目录限制保护）；"
        "python 仅允许 python -c '<纯计算代码>'，禁止文件/网络/子进程操作。"
    )
    args_schema: type[BaseModel] = BashParams

    allowed_dir: str | None = None

    def _run(self, command: str) -> str:
        # 安全校验
        err = _validate_bash_command(command, self.allowed_dir)
        if err:
            return err

        cwd = self.allowed_dir if self.allowed_dir else os.getcwd()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                encoding='utf-8',
                errors='replace',
                timeout=BASH_TIMEOUT,
                cwd=cwd,
            )
            out = result.stdout
            err = result.stderr
            parts = []
            if out:
                parts.append(f"STDOUT:\n{out.rstrip()}")
            if err:
                parts.append(f"STDERR:\n{err.rstrip()}")
            if not parts:
                parts.append("(无输出，命令执行成功)")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"错误：命令执行超时（{BASH_TIMEOUT}秒）"
        except Exception as e:
            return f"错误：{e}"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError


class EditFileParams(BaseModel):
    path: str = Field(description="要编辑的文件路径（绝对路径）")
    old_string: str = Field(description="要替换的原文字段（必须与文件中的内容完全一致）")
    new_string: str = Field(description="替换后的文字")


class EditFileTool(BaseTool):
    """在文件中精确查找并替换指定文本。

    只替换第一个匹配项。old_string 必须与文件中的内容完全一致（包括空白字符）。
    替换成功后返回前后几行的预览。
    """

    name: str = "edit_file"
    description: str = (
        "在文件中精确查找并替换指定文本。old_string 必须与文件中的内容完全一致。"
        "只替换第一个匹配项。替换成功后返回修改位置前后的预览。"
    )
    args_schema: type[BaseModel] = EditFileParams

    allowed_dir: str | None = None

    def _run(self, path: str, old_string: str, new_string: str) -> str:
        err = _validate_file_path(path, self.allowed_dir)
        if err:
            return err
        if not old_string:
            return "错误：old_string 不能为空"

        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return f"错误：文件不存在 — {path}"
        except Exception as e:
            return f"读取文件失败：{e}"

        idx = content.find(old_string)
        if idx == -1:
            lines = content.split("\n")
            line_count = len(lines)
            # 尝试提供上下文提示
            snippet = content[:200] if len(content) <= 200 else content[:200] + "..."
            return (
                f"未找到匹配文本（文件共 {line_count} 行，{len(content)} 字符）。\n"
                f"文件开头预览:\n{snippet}\n\n"
                f"请确认 old_string 与文件内容完全一致（含空白字符）。"
            )

        new_content = content[:idx] + new_string + content[idx + len(old_string):]

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return f"写入文件失败：{e}"

        # 生成预览：定位到匹配所在行，显示前后行
        lines = content.split("\n")
        # 找到匹配所在的行号
        pos = 0
        match_line_idx = 0
        for i, line in enumerate(lines):
            if pos + len(line) > idx:
                match_line_idx = i
                break
            pos += len(line) + 1  # +1 for \n
        # 取前后行（存在时）
        prev_snippet = lines[match_line_idx - 1].strip()[-60:] if match_line_idx > 0 else ""
        match_snippet = lines[match_line_idx].strip()[:80]
        next_snippet = lines[match_line_idx + 1].strip()[:60] if match_line_idx + 1 < len(lines) else ""
        preview_parts = []
        if prev_snippet:
            preview_parts.append(f"...{prev_snippet}")
        preview_parts.append(f"→ {match_snippet} ←")
        if next_snippet:
            preview_parts.append(f"{next_snippet}...")

        return (
            f"替换成功。已将 \"{old_string}\" 替换为 \"{new_string}\"。\n"
            f"修改位置预览:\n" + "\n".join(preview_parts)
        )

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError


# ─── FileReadTool ────────────────────────────────────────────

class FileReadParams(BaseModel):
    path: str = Field(description="要读取的文件路径（绝对路径）")


def _validate_file_path(path: str, allowed_dir: str | None) -> str | None:
    """校验文件路径是否在 allowed_dir 内。返回错误消息，通过返回 None。

    使用 realpath 归一化，可拦截 `..`、绝对路径穿越与符号链接逃逸。
    """
    if not allowed_dir:
        return None
    allowed = os.path.realpath(os.path.abspath(allowed_dir))
    target = os.path.realpath(os.path.abspath(path))
    if target == allowed or target.startswith(allowed + os.sep):
        return None
    return f"错误：禁止访问 allowed_dir 外的路径: {path}"


class FileReadTool(BaseTool):
    """读取文件内容。比 bash cat/python -c 更简单可靠。"""

    name: str = "read_file"
    description: str = "读取指定文件的全部内容。返回文件文本。优先用这个工具而不是 bash 来读取文件。"
    args_schema: type[BaseModel] = FileReadParams

    allowed_dir: str | None = None

    def _run(self, path: str) -> str:
        err = _validate_file_path(path, self.allowed_dir)
        if err:
            return err
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            return f"文件内容 ({len(content)} 字符):\n\n{content}"
        except Exception as e:
            return f"读取文件失败：{e}"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError


# ─── FileWriteTool ───────────────────────────────────────────

class FileWriteParams(BaseModel):
    path: str = Field(description="要写入的文件路径（绝对路径）")
    content: str = Field(description="要写入文件的完整内容")


class FileWriteTool(BaseTool):
    """覆盖写入文件。比 bash sed/python -c 更简单可靠。"""

    name: str = "write_file"
    description: str = (
        "将完整内容写入指定文件（覆盖原内容）。"
        "优先用这个工具而不是 bash 来写入/修改文件。"
    )
    args_schema: type[BaseModel] = FileWriteParams

    allowed_dir: str | None = None

    def _run(self, path: str, content: str) -> str:
        err = _validate_file_path(path, self.allowed_dir)
        if err:
            return err
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"文件已成功写入 ({len(content)} 字符): {path}"
        except Exception as e:
            return f"写入文件失败：{e}"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError
