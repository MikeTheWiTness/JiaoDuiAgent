"""校对报告 → Word 批注版（docx）生成器。

将试卷/讲义目录下各题（单元N/第N题/板块N）的 `_校对报告.md` 合并为单个 docx：
- `【N|原|改】` 标记 → Word 批注（改后文字 + 修改原因）
- 图片合并（重命名防冲突）并嵌入
- 每题一级标题 + 分页符

依赖 pandoc（`-f markdown-implicit_figures` 防止图片题注污染）。
"""
import itertools
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from core.logging_utils import log
from core.pandoc_utils import find_pandoc

_PAT = re.compile(r"【(\d+)\|([^】]*)】", re.DOTALL)
_PAGE_BREAK = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```'

_NS = ('xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
       'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
       'xmlns:o="urn:schemas-microsoft-com:office:office" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
       'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'mc:Ignorable="w14"')


def generate_combined_docx(paper_dir: str, out_dir: str | None = None) -> str | None:
    """扫描试卷/讲义目录，生成一份带批注的合并 Word 报告。

    Args:
        paper_dir: 拆分结果目录（含 单元N/第N题 子目录 + _校对报告.md + images/）
        out_dir: 输出目录，默认 paper_dir 同级 校对Word/

    Returns:
        docx 路径，失败返回 None
    """
    paper_path = Path(paper_dir)
    if not paper_path.is_dir():
        log(f"❌ Word 报告：目录不存在 {paper_dir}")
        return None

    if not find_pandoc():
        log("❌ Word 报告：Pandoc 未安装，无法生成")
        return None

    questions = _collect_reports(paper_path)
    if not questions:
        log(f"⚠️ Word 报告：{paper_dir} 下未找到任何 _校对报告.md")
        return None

    out_root = Path(out_dir) if out_dir else paper_path.parent / "校对Word"
    out_root.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in paper_path.name if c not in r'\/:*?"<>|')
    out_path = out_root / f"{safe_name}_校对批注版.docx"

    work = Path(tempfile.mkdtemp(prefix="_docx_report_"))
    img_root = work / "images"
    img_root.mkdir(exist_ok=True)

    try:
        comments = {}
        gid_iter = itertools.count(1)
        used_ids = set()
        all_bodies = []

        for qid, part in questions:
            marker_idx = part.find("### 标记原文")
            reason_idx = part.find("### 修改原因")
            if marker_idx == -1 or reason_idx == -1 or reason_idx < marker_idx:
                log(f"   ⚠️ Word 报告：{qid} 分段异常，跳过")
                continue
            reasons = _parse_reasons(part[reason_idx:])
            body = part[marker_idx:reason_idx]
            body = "\n".join(
                l for l in body.splitlines()
                if not (l.strip().startswith("### 标记原文")
                        or l.strip().startswith("编号：")
                        or l.strip().startswith("内容："))
            ).strip()
            body = _rewrite_images(body, paper_path / qid, img_root)
            body = _convert_multiline_tables(body)
            body = _preprocess_latex(body)

            def _repl(m, _reasons=reasons):
                cid = int(m.group(1))
                rest = m.group(2)
                if "|" not in rest:
                    return m.group(0)
                orig, new = rest.split("|", 1)
                gid = next(gid_iter)
                if gid in used_ids:
                    gid = max(used_ids) + 1
                used_ids.add(gid)
                if orig.endswith("\\") and not orig.endswith("\\\\"):
                    orig = orig + "\\"
                comments[gid] = (new, _reasons.get(cid))
                start = f'`<w:commentRangeStart w:id="{gid}"/>`{{=openxml}}'
                end = (f'`<w:commentRangeEnd w:id="{gid}"/>'
                       f'<w:r><w:commentReference w:id="{gid}"/></w:r>`{{=openxml}}')
                return start + orig + end

            unit_body = _PAT.sub(_repl, body)
            all_bodies.append(f"# {qid}\n\n{unit_body}\n\n{_PAGE_BREAK}")

        if not comments:
            log(f"⚠️ Word 报告：{paper_dir} 无任何可处理的批注标记")
            return None

        full_md = "\n\n".join(all_bodies)
        md_tmp = work / "_报告_带锚.md"
        md_tmp.write_text(full_md, encoding="utf-8")

        r = subprocess.run(
            [find_pandoc(), "-f", "markdown-implicit_figures",
             str(md_tmp), "-o", str(out_path)],
            capture_output=True, text=True, cwd=str(work))
        if r.returncode != 0:
            log(f"❌ Word 报告：pandoc 转换失败: {r.stderr[:300]}")
            return None
        if r.stderr.strip():
            fetch_warns = [l for l in r.stderr.splitlines() if 'fetch' in l]
            if fetch_warns:
                log(f"   ⚠️ Word 报告：{len(fetch_warns)} 张图片未找到（将显示替换文字）")

        _inject_comments(out_path, comments)
        log(f"✅ Word 批注报告已生成：{out_path}（{len(comments)} 条批注）")
        return str(out_path)
    except Exception as e:
        import traceback
        log(f"❌ Word 报告生成异常: {e}\n{traceback.format_exc()}")
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _collect_reports(paper_path: Path):
    """收集子目录（单元N/第N题/板块N）的 _校对报告.md，按数字排序。"""
    reports = []
    for sub in paper_path.iterdir():
        if not sub.is_dir():
            continue
        rep = sub / "_校对报告.md"
        if rep.exists():
            try:
                reports.append((sub.name, rep.read_text(encoding="utf-8")))
            except OSError:
                continue

    def _sort_key(item):
        m = re.findall(r"\d+", item[0])
        return (int(m[0]) if m else 9999, item[0])

    return sorted(reports, key=_sort_key)


def _parse_reasons(part: str) -> dict:
    reasons = {}
    for line in part.splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if m:
            reasons[int(m.group(1))] = m.group(2).strip()
    return reasons


def _rewrite_images(body: str, q_dir: Path, img_root: Path) -> str:
    """图片引用重写：./images/xxx → ./images/{题名}_xxx，复制到合并目录防编号冲突。"""
    q_img_dir = q_dir / "images"

    def _repl(m):
        name = Path(m.group(2)).name
        new_name = f"{q_dir.name}_{name}"
        src_img = q_img_dir / name
        if src_img.exists():
            try:
                shutil.copy2(src_img, img_root / new_name)
            except OSError:
                pass
        alt = m.group(1)
        if alt.startswith("@@@"):
            alt = "配图"
        return f"![{alt}](./images/{new_name})"

    return re.sub(r"!\[([^]]*)\]\(([^)]+)\)", _repl, body)


def _convert_multiline_tables(text: str) -> str:
    """多行表格（长 --- 线包裹，pandoc multiline table）→ grid table。

    pandoc 的 multiline table 单元格会丢弃 openxml raw；grid table 正常。
    短 --- 是 markdown 分隔线，不动。
    """
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        # 仅「整行全部由 - 组成」的长线才是 multiline table 边框；- 开头的列表项不算
        if set(stripped) == {"-"} and len(stripped) >= 10:
            j = i + 1
            end = -1
            while j < n:
                s = lines[j].strip()
                if set(s) == {"-"} and len(s) >= 10:
                    end = j
                    break
                j += 1
            if end != -1:
                rows = []
                for k in range(i + 1, end):
                    s = lines[k].strip()
                    if not s:
                        continue
                    if set(s.replace(" ", "")) <= {"-"}:
                        continue
                    cells = [c.strip() for c in re.split(r" {2,}", s)]
                    rows.append(cells)
                if rows:
                    ncols = max(len(r) for r in rows)
                    rows = [r + [""] * (ncols - len(r)) for r in rows]
                    widths = [0] * ncols
                    for r in rows:
                        for ci, c in enumerate(r):
                            widths[ci] = max(widths[ci], len(c))

                    def border(ch):
                        return "+" + "+".join(ch * (w + 2) for w in widths) + "+"

                    out.append(border("-"))
                    out.append("| " + " | ".join(
                        c.ljust(widths[ci]) for ci, c in enumerate(rows[0])) + " |")
                    out.append(border("="))
                    for r in rows[1:]:
                        out.append("| " + " | ".join(
                            c.ljust(widths[ci]) for ci, c in enumerate(r)) + " |")
                        out.append(border("-"))
                    i = end + 1
                    continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _preprocess_latex(body: str) -> str:
    """LaTeX 定界符还原：\\[...\\] / \\[...\\] → 美元行内公式；转义美元还原；公式内部双反斜杠命令还原。"""
    body = re.sub(r"\\\\\[(.*?)\\\\]",
                  lambda m: "$" + m.group(1).replace("\\\\", "\\") + "$",
                  body, flags=re.DOTALL)
    body = re.sub(r"\\\[(.*?)\\\]", lambda m: "$" + m.group(1) + "$",
                  body, flags=re.DOTALL)
    body = body.replace("\\$", "$")
    body = re.sub(r"\$(.+?)\$",
                  lambda m: "$" + m.group(1).replace("\\\\", "\\") + "$",
                  body, flags=re.DOTALL)
    body = _normalize_math_dollars(body)
    return body


def _normalize_math_dollars(text: str) -> str:
    """规范化数学定界符，防止 pandoc 错配吞掉 openxml raw。

    `$200\\Omega $`（$ 内尾随空格）不闭合时，pandoc 会把后续文本中的下一个
    `$` 与它配对成数学，中间的 openxml raw 被吞进公式导致批注锚点丢失。
    """
    text = re.sub(r"\$([^$\n]*?)[ \t]+\$", lambda m: "$" + m.group(1) + "$", text)
    text = re.sub(r"\$[ \t]+([^$\n]*?)\$", lambda m: "$" + m.group(1) + "$", text)
    lines = []
    for line in text.split("\n"):
        if line.count("$") % 2 == 1:
            idx = line.rfind("$")
            line = line[:idx] + "\\$" + line[idx + 1:]
        lines.append(line)
    return "\n".join(lines)


def _inject_comments(docx_path: Path, comments: dict):
    """填充 comments.xml、清理无锚点引用、替换图片替换文字。"""
    # 先读 document.xml 计算保留的批注 id（zipfile 部件顺序不保证 document.xml 在前）
    kept_ids = set()
    with zipfile.ZipFile(docx_path, "r") as zin:
        doc_xml = zin.read("word/document.xml").decode("utf-8")
    doc_xml = re.sub(r'descr="@@@[^"]*"', 'descr="配图"', doc_xml)
    doc_xml, kept_ids = _strip_unanchored_comments(doc_xml)

    comments_xml = _build_comments_xml(comments, kept_ids)
    tmp_path = docx_path.with_name("_tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, \
            zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = doc_xml.encode("utf-8")
            elif item.filename == "word/comments.xml":
                data = comments_xml.encode("utf-8")
            zout.writestr(item, data)
    tmp_path.replace(docx_path)


def _strip_unanchored_comments(doc_xml: str):
    """删除无 commentRangeStart 配对的 commentRangeEnd + commentReference。

    源数据损坏（如标记被插进图片引用内部）导致部分锚点缺失时，
    移除对应引用，避免 Word 打开异常。
    """
    starts = set(re.findall(r'<w:commentRangeStart w:id="(\d+)"', doc_xml))
    for cid in re.findall(r'<w:commentReference w:id="(\d+)"', doc_xml):
        if cid not in starts:
            doc_xml = re.sub(r'<w:commentRangeEnd w:id="%s"\s*/>' % cid, '', doc_xml)
            doc_xml = re.sub(r'<w:r><w:commentReference w:id="%s"\s*/></w:r>' % cid, '', doc_xml)
    return doc_xml, starts


def _build_comments_xml(comments: dict, kept_ids: set) -> str:
    items = []
    for gid in sorted(comments):
        if str(gid) not in kept_ids:
            continue
        new, reason = comments[gid]
        paras = [f'<w:p><w:r><w:t xml:space="preserve">{escape(new)}</w:t></w:r></w:p>']
        if reason:
            paras.append(
                f'<w:p><w:r><w:t xml:space="preserve">修改原因：'
                f'{escape(reason)}</w:t></w:r></w:p>')
        items.append(
            f'<w:comment w:id="{gid}" w:author="校对助手" '
            f'w:date="2026-08-05T10:00:00Z">' + "".join(paras) + '</w:comment>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:comments {_NS}>' + "".join(items) + "</w:comments>")
