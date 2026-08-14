"""校对报告 → Word 批注版（docx）生成器。

将试卷/讲义目录下各题（单元N/第N题/板块N）的 `_校对报告.md` 合并为单个 docx：
- `【N|原|改】` 标记 → Word 批注（改后文字 + 修改原因）
- 图片合并（重命名防冲突）并嵌入；外链/缺失引用转为文字说明
- 每题一级标题 + 分页符；「无问题」单元同样列入报告并标注
- 含批注标记但缺分段的单元（批注可能丢失）跳过并警示

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
from shared.comment_marker import scan_math_spans as _scan_math_spans
from shared.formula_render import latex_to_png

# \| 是 LaTeX 转义竖线（\left\|…\right\|），整体属于原文字段，不得当分隔符
_PAT = re.compile(r"【(\d+)\|((?:\\\||[^|])*)\|([^】]*?)】", re.DOTALL)
_PAGE_BREAK = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```'

_NS = ('xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
       'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
       'xmlns:o="urn:schemas-microsoft-com:office:office" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
       'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
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
    # 必须绝对化：pandoc 以临时目录为 cwd，相对 out_dir 会把 docx 写进临时目录，
    # 后续 _inject_comments 按调用方 cwd 打开相对路径必然 FileNotFoundError
    out_root = out_root.resolve()
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
        skipped_anchors = {}
        skip_anchor_iter = itertools.count(1)
        heading_anchors = {}
        all_bodies = []
        skipped_clean = 0
        skipped_broken = 0

        for qid, part in questions:
            marker_idx = part.find("### 标记原文")
            reason_idx = part.find("### 修改原因")
            if marker_idx == -1 or reason_idx == -1 or reason_idx < marker_idx:
                # 无分段不一定是异常：LLM 判定「无问题」时报告只有
                # 「无问题 + 工具日志 + 思考过程」，无批注分段属正常形态。
                # 含批注标记（【N|原|改】）却缺分段才可疑——批注可能丢失。
                if _PAT.search(part):
                    skipped_broken += 1
                    log(f"   ⚠️ Word 报告：{qid} 含批注标记但缺少「标记原文/修改原因」分段，跳过（批注无法生成）")
                else:
                    skipped_clean += 1
                    log(f"   ℹ️ Word 报告：{qid} 无批注，插入单元原文 + 「无问题」批注（锚定标题）")
                    unit_md = paper_path / qid / f"{qid}.md"
                    if unit_md.exists():
                        content = unit_md.read_text(encoding="utf-8").strip()
                        content = _rewrite_images(content, paper_path / qid, img_root)
                        content = _preprocess_latex(content)
                        gid = next(gid_iter)
                        if gid in used_ids:
                            gid = max(used_ids) + 1
                        used_ids.add(gid)
                        comments[gid] = ("无问题", None)
                        # 锚点后处理落在标题「qid」文本上（Heading1 段落内）
                        heading_anchors[gid] = qid
                        all_bodies.append(f"# {qid}\n\n{content}\n\n{_PAGE_BREAK}")
                    else:
                        all_bodies.append(f"# {qid}\n\n无问题\n\n{_PAGE_BREAK}")
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

            # 行内公式区间（$...$ 配对），锚点落在公式内部的标记跳过——
            # 上游数据把公式内部文本当锚点时，插入 openxml 会撕裂公式导致乱码
            math_spans = _scan_math_spans(body)

            def _repl(m, _reasons=reasons):
                cid = int(m.group(1))
                orig = m.group(2)
                new = m.group(3)
                if any(s <= m.start() < e for s, e in math_spans):
                    # 唯一占位符代替还原文本：pandoc 转换后据此精确定位公式高亮，
                    # 避免还原文本（如常见变量 v）误匹配其他公式。
                    # 记录 (原文, 修改意见)，高亮处一并显示修改建议。
                    log(f"   ⚠️ Word 报告：{qid} 批注锚点位于公式内部，跳过该条（标记原文被还原）")
                    n = next(skip_anchor_iter)
                    skipped_anchors[n] = (orig.strip("$"), new.strip("$"))
                    return f"SKIPANCH{n}Z"
                gid = next(gid_iter)
                if gid in used_ids:
                    gid = max(used_ids) + 1
                used_ids.add(gid)
                if orig.endswith("\\") and not orig.endswith("\\\\"):
                    orig = orig + "\\"
                # 锚点文本内 $ 不成对（奇数个）时转义：防与正文其他公式的 $
                # 配对，吞掉 openxml raw。成对的完整公式（$...$）保持原样转公式。
                if orig.count("$") % 2 == 1:
                    orig = orig.replace("$", "\\$")
                comments[gid] = (new, _reasons.get(cid))
                start = f'`<w:commentRangeStart w:id="{gid}"/>`{{=openxml}}'
                end = (f'`<w:commentRangeEnd w:id="{gid}"/>'
                       f'<w:r><w:commentReference w:id="{gid}"/></w:r>`{{=openxml}}')
                return start + orig + end

            unit_body = _PAT.sub(_repl, body)
            unit_body = _textify_skipped_formulas(unit_body, skipped_anchors)
            all_bodies.append(f"# {qid}\n\n{unit_body}\n\n{_PAGE_BREAK}")

        if not all_bodies:
            log(f"⚠️ Word 报告：{paper_dir} 无任何可处理的单元")
            return None

        full_md = "\n\n".join(all_bodies)
        md_tmp = work / "_报告_带锚.md"
        md_tmp.write_text(full_md, encoding="utf-8")

        r = subprocess.run(
            [find_pandoc(), "-f", "markdown-implicit_figures+hard_line_breaks+mark",
             str(md_tmp), "-o", str(out_path)],
            capture_output=True, text=True, cwd=str(work))
        if r.returncode != 0:
            log(f"❌ Word 报告：pandoc 转换失败: {r.stderr[:300]}")
            return None
        if r.stderr.strip():
            fetch_warns = [l for l in r.stderr.splitlines() if 'fetch' in l]
            if fetch_warns:
                log(f"   ⚠️ Word 报告：{len(fetch_warns)} 张图片未找到（将显示替换文字）")

        _inject_comments(out_path, comments, heading_anchors)
        summary = f"（{len(comments)} 条批注"
        if skipped_clean:
            summary += f"，{skipped_clean} 个单元无批注"
        if skipped_broken:
            summary += f"，{skipped_broken} 个单元含标记但缺分段跳过"
        log(f"✅ Word 批注报告已生成：{out_path}{summary}）")
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
    """图片引用重写：./images/xxx → ./images/{题名}_xxx，复制到合并目录防编号冲突。

    外链 https:// 引用是 LLM 幻觉（搜索结果拷贝），转为文字说明，
    避免 pandoc 尝试下载失败产生 fetch 警告。
    """
    q_img_dir = q_dir / "images"

    def _repl(m):
        ref = m.group(2)
        if ref.startswith(("http://", "https://")):
            return "（配图缺失：外链图片无法嵌入）"
        name = Path(ref).name
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


def _inject_comments(docx_path: Path, comments: dict, heading_anchors: dict | None = None):
    """填充 comments.xml、清理无锚点引用、替换图片替换文字。

    批注内 `$...$` 公式渲染为 PNG 图片注入（shared/formula_render），
    渲染失败（含中文/矩阵等）的公式段降级为原 LaTeX 文本。
    heading_anchors：{gid: 标题文本}，批注锚点后处理落在 Heading1 段落
    的标题文本 run 上（pandoc 会忽略标题内的 raw 标记，只能转换后注入）。
    """
    # 先读 document.xml 计算保留的批注 id（zipfile 部件顺序不保证 document.xml 在前）
    kept_ids = set()
    with zipfile.ZipFile(docx_path, "r") as zin:
        doc_xml = zin.read("word/document.xml").decode("utf-8")
    doc_xml = re.sub(r'descr="@@@[^"]*"', 'descr="配图"', doc_xml)
    if heading_anchors:
        doc_xml = _anchor_heading_comments(doc_xml, heading_anchors)
    doc_xml, kept_ids = _strip_unanchored_comments(doc_xml)

    work_dir = Path(tempfile.mkdtemp(prefix="_cmt_img_", dir=str(docx_path.parent)))
    try:
        comments_xml, images = _build_comments_xml(comments, kept_ids, work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    tmp_path = docx_path.with_name("_tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, \
            zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = doc_xml.encode("utf-8")
            elif item.filename == "word/comments.xml":
                data = comments_xml.encode("utf-8")
            elif item.filename == "[Content_Types].xml" and images:
                data = _ensure_png_content_type(data)
            zout.writestr(item, data)
        if images:
            # 批注公式图片 part + 关系（新建 comments.xml.rels）
            for media_name, png_bytes, r_id in images:
                zout.writestr(f"word/media/{media_name}", png_bytes)
            rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        + "".join(
                            f'<Relationship Id="{r_id}" '
                            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                            f'Target="media/{media_name}"/>'
                            for media_name, _, r_id in images)
                        + "</Relationships>")
            zout.writestr("word/_rels/comments.xml.rels", rels_xml.encode("utf-8"))
    tmp_path.replace(docx_path)


def _ensure_png_content_type(ct_xml: bytes) -> bytes:
    """确保 [Content_Types].xml 含 png Default 声明（批注公式图片需要）。"""
    text = ct_xml.decode("utf-8")
    if 'Extension="png"' in text:
        return ct_xml
    return text.replace(
        '<Default Extension="rels"',
        '<Default Extension="png" ContentType="image/png" />\n<Default Extension="rels"',
    ).encode("utf-8")


_SKIP_ANCHOR_RE = re.compile(r"SKIPANCH(\d+)Z")


def _textify_skipped_formulas(text: str, skipped_anchors: dict) -> str:
    """把含被跳过标记的公式改为转义文本并用 ==...== 高亮，不转微软公式。

    公式内标记被跳过（批注无法生成）时，正文对应公式以 LaTeX 文本原样显示
    并黄色高亮，提示读者该处有问题。`\\`、`$` 与 `^` 转义避免 pandoc 数学
    解析、markdown 转义吞字符与 `^...^` 上标误判；SKIPANCH{n}Z 占位符还原
    为标记原文，并在高亮内附修改意见（原文→改后）。
    """
    if not skipped_anchors:
        return text
    spans = _scan_math_spans(text)
    out = text
    for s, e in reversed(spans):
        seg = out[s:e]
        if "SKIPANCH" not in seg:
            continue
        seg = seg.replace("\\", "\\\\").replace("$", "\\$").replace("^", "\\^")

        def _esc(t):
            return t.replace("\\", "\\\\").replace("$", "\\$").replace("^", "\\^")

        # 先收集修改意见（转义不影响占位符），再还原原文，意见追加在公式文本之后
        notes = "".join(
            f"（修改意见：{_esc(orig)}→{_esc(new)}）" if new else ""
            for m in _SKIP_ANCHOR_RE.finditer(seg)
            for orig, new in [skipped_anchors[int(m.group(1))]])
        seg = _SKIP_ANCHOR_RE.sub(
            lambda m: _esc(skipped_anchors[int(m.group(1))][0]), seg)
        out = out[:s] + "==" + seg + notes + "==" + out[e:]
    return out


def _anchor_heading_comments(doc_xml: str, heading_anchors: dict) -> str:
    """在 Heading1 段落的标题文本 run 上插入批注锚点。

    pandoc 忽略标题（ATX heading）内的 raw 标记，无问题单元的「无问题」
    批注锚点只能在此转换后处理：匹配 pStyle=Heading1 段落中 w:t 文本等于
    标题文本的 run，在 run 前后插入 commentRangeStart/End + commentReference。
    """
    for gid, title in heading_anchors.items():
        # rangeStart 在 run 前、rangeEnd+reference 在 run 后（与 pandoc 正常锚点同构）。
        # rPr 用「自闭合元素序列」匹配（pandoc rPr 子元素均为自闭合），
        # 避免 .*? 回溯跨段匹配到远处标题段。
        pat = re.compile(
            r'(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"[^>]*/>\s*</w:pPr>\s*)'
            r'(<w:r>\s*<w:rPr>\s*(?:<w:[^>]*/>\s*)*</w:rPr>\s*<w:t[^>]*>)('
            + re.escape(title) + r')(</w:t>\s*</w:r>)(\s*</w:p>)', re.DOTALL)

        def _repl(m, _gid=gid):
            return (m.group(1)
                    + f'<w:commentRangeStart w:id="{_gid}"/>'
                    + m.group(2) + m.group(3) + m.group(4)
                    + f'<w:commentRangeEnd w:id="{_gid}"/>'
                    + f'<w:r><w:commentReference w:id="{_gid}"/></w:r>'
                    + m.group(5))

        doc_xml = pat.sub(_repl, doc_xml)
    return doc_xml


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


def _build_comments_xml(comments: dict, kept_ids: set, work_dir: Path) -> tuple[str, list]:
    """构建 comments.xml，批注内 `$...$` 公式渲染为 PNG 图片。

    Args:
        comments: gid → (改后文字, 修改原因)
        kept_ids: 保留的批注 id
        work_dir: 公式 PNG 渲染临时目录

    Returns:
        (comments_xml, images)：images 为 [(media文件名, png字节, rId), ...]
    """
    items = []
    images = []
    pic_id = itertools.count(1)

    def _escape_run(text: str) -> str:
        return f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

    def _para_with_formulas(text: str) -> str:
        """文本按 $...$ 切分：公式段渲染图片（失败降级为文本），其余保留文本。"""
        parts = re.split(r'(\$[^$]+\$)', text)
        runs = []
        for part in parts:
            if not part:
                continue
            if part.startswith("$") and part.endswith("$") and len(part) > 2:
                body = part[1:-1]
                num = next(pic_id)
                media_name = f"comment_pic{num}.png"
                if latex_to_png(body, work_dir / media_name):
                    png_bytes = (work_dir / media_name).read_bytes()
                    r_id = f"rIdPic{len(images) + 1}"
                    images.append((media_name, png_bytes, r_id))
                    runs.append(_inline_image_xml(num, media_name, r_id, png_bytes))
                    continue
            runs.append(_escape_run(part))
        return "".join(runs)

    for gid in sorted(comments):
        if str(gid) not in kept_ids:
            continue
        new, reason = comments[gid]
        center = '<w:pPr><w:jc w:val="center"/></w:pPr>'
        paras = [f"<w:p>{center}{_para_with_formulas(new)}</w:p>"]
        if reason:
            paras.append(f"<w:p>{center}{_escape_run('修改原因：')}{_para_with_formulas(reason)}</w:p>")
        items.append(
            f'<w:comment w:id="{gid}" w:author="校对助手" '
            f'w:date="{_comment_timestamp()}">' + "".join(paras) + '</w:comment>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:comments {_NS}>' + "".join(items) + "</w:comments>"), images


def _inline_image_xml(num: int, media_name: str, r_id: str, png_bytes: bytes) -> str:
    """构造批注内联图片 run 的 XML（EMU 尺寸按 200dpi 渲染物理尺寸换算）。

    图片垂直位置保持 Word 默认（底边对齐基线），不做 w:position 偏移。
    """
    from PIL import Image
    import io
    with Image.open(io.BytesIO(png_bytes)) as im:
        w_px, h_px = im.size
    emu_w = round(w_px * 914400 / 200)
    emu_h = round(h_px * 914400 / 200)
    return (
        '<w:r><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{emu_w}" cy="{emu_h}"/>'
        f'<wp:docPr id="{num}" name="{escape(media_name)}" descr="公式"/>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic>'
        f'<pic:nvPicPr><pic:cNvPr id="{num}" name="{escape(media_name)}"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill>'
        f'<a:blip r:embed="{r_id}"/><a:stretch><a:fillRect/></a:stretch>'
        '</pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{emu_w}" cy="{emu_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic>'
        '</wp:inline></w:drawing></w:r>'
    )


def _comment_timestamp() -> str:
    """生成 OOXML ST_DateTime 格式的当前 UTC 时间戳（ISO 8601 Z 形式）。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
