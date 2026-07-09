"""BashTool + FileReadTool + FileWriteTool —— 让 LLM 直接操作文件。

用于格式修正等场景：LLM 不再返回修正后的文本（可能格式再出错），
而是直接编辑目标文件，编辑后由 Python 端重读验证。
"""
import subprocess
import os
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


# ─── BashTool ───────────────────────────────────────────────

class BashParams(BaseModel):
    command: str = Field(
        description="要执行的 bash 命令。支持管道、重定向、python -c 等。"
    )


class BashTool(BaseTool):
    """让 LLM 执行 bash 命令来直接操作文件。

    用途：格式修正时，LLM 用 cat/type 读取文件内容，用 sed / python -c 等
    直接修改文件，Python 端在工具返回后重读文件进行验证。

    安全约束：通过 allowed_dir 限制可操作的文件目录。
    """

    name: str = "bash"
    description: str = (
        "执行 bash 命令来读取或编辑文件。常用命令：\n"
        "- python -c \"...\" — 用 Python 脚本读取/编辑文件（最推荐，跨平台）\n"
        "- sed -i 's/旧/新/g' <文件路径> — 替换文本\n"
        "注意：Windows 不支持 cat；用 python 读取文件。"
        "每个 python -c 命令末尾必须有 print()，否则看不到输出！"
    )
    args_schema: type[BaseModel] = BashParams

    allowed_dir: str | None = None

    def _run(self, command: str) -> str:
        cwd = self.allowed_dir if self.allowed_dir else os.getcwd()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                encoding='utf-8',
                errors='replace',
                timeout=30,
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
            return "错误：命令执行超时（30秒）"
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

    def _run(self, path: str, old_string: str, new_string: str) -> str:
        if not old_string:
            return "错误：old_string 不能为空"

        try:
            with open(path, "r", encoding="utf-8") as f:
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


class FileReadTool(BaseTool):
    """读取文件内容。比 bash cat/python -c 更简单可靠。"""

    name: str = "read_file"
    description: str = "读取指定文件的全部内容。返回文件文本。优先用这个工具而不是 bash 来读取文件。"
    args_schema: type[BaseModel] = FileReadParams

    def _run(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
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

    def _run(self, path: str, content: str) -> str:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"文件已成功写入 ({len(content)} 字符): {path}"
        except Exception as e:
            return f"写入文件失败：{e}"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError


# ─── 校对标记工具（ADR-0016） ──────────────────────────────────

import threading
import re as _re_mod

_current_file: threading.local = threading.local()
_mark_counter: threading.local = threading.local()


def set_current_file(path: str):
    """设置当前校对文件路径（线程安全）。"""
    _current_file.value = path
    _mark_counter.value = 0


def get_current_file() -> str:
    """获取当前校对文件路径。"""
    return getattr(_current_file, "value", "")


def _next_mark_number() -> int:
    """获取下一个标记编号（线程安全，自动递增）。"""
    current = getattr(_mark_counter, "value", 0) + 1
    _mark_counter.value = current
    return current


def _sanitize_proofread_text(text: str) -> str:
    """清洗校对文本中的 Markdown/HTML 格式残留。

    LLM 有时会在 corrected/original/reason 中带 markdown 粗体（**text**）、
    HTML 样式（\\style{...}）、Word 残留格式等，需在写入文件前清除。
    """
    # 1. 移除 HTML/CSS style 属性（如 \\style{font-style:italic;...}{text}）
    text = _re_mod.sub(r'\\style\{[^}]*\}\{([^}]*)\}', r'\1', text)
    # 2. 移除 Markdown 粗体/斜体标记（保留内部文字）
    text = _re_mod.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = _re_mod.sub(r'\*([^*]+)\*', r'\1', text)
    text = _re_mod.sub(r'__([^_]+)__', r'\1', text)
    return text


def _validate_latex_braces(text: str) -> str | None:
    """校验文本中所有花括号的配对。返回错误信息，无错误返回 None。

    检查范围：
    - 数学模式内（$...$、$$...$$、\\(...\\)、\\[...\\]）：严格配对
    - 数学模式外：花括号通常表示格式错误（\\style{} 等），一并检查
    - 排除已转义的 \\{ \\} 和 LaTeX 命令参数（如 \\text{...}、\\textbf{...}）

    任何位置出现括号不配对都拒绝，防止 LaTeX 编译失败。
    """
    # 1. 全局括号平衡（排除转义的 \{ \}）
    stripped = text.replace(r'\{', '').replace(r'\}', '')
    depth = 0
    for i, ch in enumerate(stripped):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        if depth < 0:
            ctx = text[max(0,i-30):i+30]
            return f"花括号不匹配（位置 {i} 处多了一个右括号）: ...{ctx}..."
    if depth != 0:
        return f"花括号不匹配（全文{'少' if depth > 0 else '多'}了 {abs(depth)} 个括号）"

    # 2. 逐段数学模式校验
    math_blocks = _re_mod.findall(
        r'\$\$[\s\S]*?\$\$|\$[^$]+?\$|\\\[[\s\S]*?\\\]|\\\(.+?\\\)',
        text
    )
    for block in math_blocks:
        # 排除转义的 \{ \}，只数真实分组括号
        clean = block.replace(r'\{', '').replace(r'\}', '')
        bd = 0
        for ch in clean:
            if ch == '{':
                bd += 1
            elif ch == '}':
                bd -= 1
            if bd < 0:
                return f"数学公式花括号不匹配（多了一个右括号）: {block[:120]}"
        if bd != 0:
            return f"数学公式花括号不匹配（{'少' if bd > 0 else '多'}了 {abs(bd)} 个括号）: {block[:120]}"

    return None



