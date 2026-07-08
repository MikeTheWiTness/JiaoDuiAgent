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


class AddProofreadMarkParams(BaseModel):
    paragraph: int = Field(description="段落号（1-based，LLM 通过 read_section 已知）")
    original: str = Field(description="要标记的原文片段（短字符串）")
    occurrence: int = Field(default=1, description="该片段在段落中的第几次出现（默认为1）")
    corrected: str = Field(description="修改后的文字")
    reason: str = Field(description="修改原因")


class AddProofreadMarkTool(BaseTool):
    """在文件中添加校对标记 【N|原文|改为】，并追加修改原因。"""

    name: str = "add_proofread_mark"
    description: str = (
        "在文件中添加一处校对标记。在指定段落的第N次出现的原文处插入 "
        "【编号|原文|改为】标记，并将修改原因记录到 ### 修改原因 章节。"
    )
    args_schema: type[BaseModel] = AddProofreadMarkParams

    def _run(self, paragraph: int, original: str, occurrence: int = 1,
             corrected: str = "", reason: str = "") -> str:
        file_path = get_current_file()
        if not file_path:
            return "错误：未设置当前校对文件。"

        if not original:
            return "错误：original 不能为空"

        # 清洗 LLM 可能误带的 Markdown/HTML 格式
        original = _sanitize_proofread_text(original)
        corrected = _sanitize_proofread_text(corrected)
        reason = _sanitize_proofread_text(reason)

        # 校验 LaTeX 公式括号匹配（数学学科防 LLM 输出 }} } 错误）
        brace_err = _validate_latex_braces(corrected)
        if brace_err:
            return f"拒绝：corrected 字段的数学公式有括号错误。{brace_err}\n请修正后重试。"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return f"错误：文件不存在 — {file_path}"
        except Exception as e:
            return f"读取文件失败：{e}"

        paragraphs = _re_mod.split(r"\n\n+", content)

        if paragraph < 1 or paragraph > len(paragraphs):
            return f"错误：段落号 {paragraph} 超出范围（文件共 {len(paragraphs)} 个段落）"

        para = paragraphs[paragraph - 1]

        # 找到第 occurrence 次出现（跳过已有标记内的文字）
        found = 0
        search_pos = 0
        replace_pos = -1
        while True:
            pos = para.find(original, search_pos)
            if pos == -1:
                break
            before = para[:pos]
            if before.count("【") == before.count("】"):
                found += 1
                if found == occurrence:
                    replace_pos = pos
                    break
            search_pos = pos + 1

        if replace_pos == -1:
            return (
                f"未在段落 {paragraph} 中找到第 {occurrence} 次出现的 \"{original}\"。\n"
                f"段落预览（前200字符）:\n{para[:200]}..."
            )

        mark_num = _next_mark_number()
        mark = f"【{mark_num}|{original}|{corrected}】"
        new_para = para[:replace_pos] + mark + para[replace_pos + len(original):]
        paragraphs[paragraph - 1] = new_para
        new_content = "\n\n".join(paragraphs)

        reason_section = "\n\n### 修改原因"
        if reason_section in new_content:
            new_content += f"\n{mark_num}. {reason}"
        else:
            new_content += f"{reason_section}\n{mark_num}. {reason}"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return f"写入文件失败：{e}"

        return f"已添加标记 {mark}（编号 {mark_num}）。原因: {reason}"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError


class UpdateProofreadMarkParams(BaseModel):
    mark_number: int = Field(description="要修改的标记编号")
    original: str | None = Field(default=None, description="新原文（不修改则留空）")
    corrected: str | None = Field(default=None, description="新修改后文字（不修改则留空）")
    reason: str | None = Field(default=None, description="新修改原因（不修改则留空）")


class UpdateProofreadMarkTool(BaseTool):
    """修改已有的校对标记。"""

    name: str = "update_proofread_mark"
    description: str = "修改已添加的校对标记。至少提供一个要修改的字段。"
    args_schema: type[BaseModel] = UpdateProofreadMarkParams

    def _run(self, mark_number: int, original: str | None = None,
             corrected: str | None = None, reason: str | None = None) -> str:
        if original is None and corrected is None and reason is None:
            return "错误：至少需要指定 original、corrected 或 reason 中的一个"

        file_path = get_current_file()
        if not file_path:
            return "错误：未设置当前校对文件。"

        # 清洗 LLM 可能误带的格式
        if original is not None:
            original = _sanitize_proofread_text(original)
        if corrected is not None:
            corrected = _sanitize_proofread_text(corrected)
        if reason is not None:
            reason = _sanitize_proofread_text(reason)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return f"读取文件失败：{e}"

        old_mark_start = f"【{mark_number}|"
        idx = content.find(old_mark_start)
        if idx == -1:
            return f"错误：未找到编号 {mark_number} 的标记"

        end = content.find("】", idx)
        if end == -1:
            return f"错误：标记 {mark_number} 格式异常"

        mark_body = content[idx + len(old_mark_start):end]
        parts = mark_body.split("|", 1)
        old_original = parts[0] if len(parts) > 0 else ""
        old_corrected = parts[1] if len(parts) > 1 else ""

        new_original = original if original is not None else old_original
        new_corrected = corrected if corrected is not None else old_corrected

        new_mark = f"【{mark_number}|{new_original}|{new_corrected}】"
        new_content = content[:idx] + new_mark + content[end + 1:]

        if reason is not None:
            reason_pat = _re_mod.compile(rf"^{mark_number}\.\s.*$", _re_mod.MULTILINE)
            new_content = reason_pat.sub(rf"{mark_number}. {reason}", new_content)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return f"写入文件失败：{e}"

        changes = []
        if original is not None:
            changes.append(f"原文: \"{old_original}\" → \"{new_original}\"")
        if corrected is not None:
            changes.append(f"改为: \"{old_corrected}\" → \"{new_corrected}\"")
        if reason is not None:
            changes.append(f"原因: \"{reason}\"")

        return f"已更新标记 {mark_number}。\n" + "\n".join(changes)

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError


# ─── XML 标记式校对工具（ADR-0019） ────────────────────────────

_MATH_DELIM = _re_mod.compile(r'\$+|\$|\$\$|\\\(|\\\)|\\\[|\\\]')

# 标记计数器（线程安全）
_mark_id_counter: threading.local = threading.local()


def _reset_mark_counter():
    """重置标记计数器（每个校对单元开始时调用）。"""
    _mark_id_counter.value = 0


def _next_mark_id() -> int:
    current = getattr(_mark_id_counter, "value", 0) + 1
    _mark_id_counter.value = current
    return current


def _auto_fix_math_tag(para: str, insert_pos: int, tag: str) -> tuple[str, int]:
    """自动修复：如果插入位置在数学模式内，将标记挪到公式外。

    - open tag → 移到公式左侧
    - close tag → 移到公式右侧
    """
    if insert_pos >= len(para):
        return para, insert_pos

    # 统计 $ 的奇偶性判断是否在 $...$ 内
    before = para[:insert_pos]
    dollar_count = before.count("$") - before.count(r"\$") * 2
    if dollar_count % 2 == 1:
        # 在 $...$ 内部
        if not tag.startswith("</mark_"):
            # open tag → 移到 $ 前面
            search_pos = insert_pos - 1
            while search_pos >= 0:
                if para[search_pos] == "$" and (search_pos == 0 or para[search_pos - 1] != "\\"):
                    return para[:search_pos] + tag + para[search_pos:], search_pos + len(tag)
                search_pos -= 1
        else:
            # close tag → 移到 $ 后面
            after = para[insert_pos:]
            for j, ch in enumerate(after):
                if ch == "$" and (j == 0 or after[j - 1] != "\\"):
                    new_pos = insert_pos + j + 1
                    return para[:new_pos] + tag + para[new_pos:], new_pos + len(tag)

    return para, insert_pos


class InsertMarkParams(BaseModel):
    paragraph: int = Field(description="段落号（1-based）")
    after_text: str = Field(description="插入位置前的文字（用于定位）")
    occurrence: int = Field(default=1, description="after_text 在段落中的第几次出现")
    action: str = Field(description="'open' 插入 <mark_N>，'close' 插入 </mark_N>")
    close_mark_id: int | None = Field(default=None, description="关闭时指定对应的标记编号")


class InsertMarkTool(BaseTool):
    """在原文中插入 XML 标记 <mark_N>...</mark_N>，不修改原文内容。"""

    name: str = "insert_mark"
    description: str = (
        "在原文中插入校对标记 <mark_N> 或 </mark_N>。不修改原文。\\n"
        "- action='open': 在指定位置后插入 <mark_N>（编号自动递增）\\n"
        "- action='close': 在指定位置后插入 </mark_N>（需传 close_mark_id）\\n"
        "标记自动放在数学公式外部。"
    )
    args_schema: type[BaseModel] = InsertMarkParams

    def _run(self, paragraph: int, after_text: str, occurrence: int = 1,
             action: str = "open", close_mark_id: int | None = None) -> str:
        if action not in ("open", "close"):
            return "错误：action 必须是 'open' 或 'close'"
        if action == "close" and close_mark_id is None:
            return "错误：action='close' 时必须传 close_mark_id"

        file_path = get_current_file()
        if not file_path:
            return "错误：未设置当前校对文件。"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return f"读取文件失败：{e}"

        paragraphs = _re_mod.split(r"\n\n+", content)
        if paragraph < 1 or paragraph > len(paragraphs):
            return f"错误：段落号 {paragraph} 超出范围（共 {len(paragraphs)} 个段落）"

        para = paragraphs[paragraph - 1]

        # 定位 after_text
        found = 0
        search_pos = 0
        insert_pos = -1
        while True:
            pos = para.find(after_text, search_pos)
            if pos == -1:
                break
            found += 1
            if found == occurrence:
                insert_pos = pos + len(after_text)
                break
            search_pos = pos + 1

        if insert_pos == -1:
            return (
                f"未找到第 {occurrence} 次出现的 \"{after_text}\"。\n"
                f"段落预览（前200字符）:\n{para[:200]}..."
            )

        # 确定标记文本
        if action == "open":
            mark_id = _next_mark_id()
            tag = f"<mark_{mark_id}>"
        else:
            tag = f"</mark_{close_mark_id}>"

        # 自动修复：检测并修正公式内的标记
        new_para, final_pos = _auto_fix_math_tag(para, insert_pos, tag)
        if final_pos != insert_pos:
            tag_note = "（已自动移到公式外）"
        else:
            tag_note = ""
            new_para = para[:insert_pos] + tag + para[insert_pos:]

        paragraphs[paragraph - 1] = new_para
        new_content = "\n\n".join(paragraphs)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return f"写入文件失败：{e}"

        return f"已插入 {tag}（段落 {paragraph}）{tag_note}"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError


class AddCorrectionParams(BaseModel):
    mark_id: int = Field(description="对应的标记编号")
    original: str = Field(description="原文片段")
    corrected: str = Field(description="修改建议")
    reason: str = Field(description="修改原因")


class AddCorrectionTool(BaseTool):
    """在文件末尾追加修改建议。"""

    name: str = "add_correction"
    description: str = "在文件末尾 ### 修改建议 章节追加一条修改建议。"
    args_schema: type[BaseModel] = AddCorrectionParams

    def _run(self, mark_id: int, original: str, corrected: str, reason: str) -> str:
        file_path = get_current_file()
        if not file_path:
            return "错误：未设置当前校对文件。"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return f"读取文件失败：{e}"

        entry = f"\n<mark_{mark_id}>: {original} → {corrected}  原因: {reason}"

        section_header = "### 修改建议"
        if section_header not in content:
            content += f"\n\n{section_header}"

        content += entry

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return f"写入文件失败：{e}"

        return f"已追加 <mark_{mark_id}> 的修改建议"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError
