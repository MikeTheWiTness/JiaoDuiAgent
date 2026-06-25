import re
import os
import zipfile
import tempfile
import shutil

from core.logging_utils import log
from core.pandoc_utils import convert_with_pandoc, check_pandoc


def normalize_text(s):
    if not s:
        return ""
    result = []
    for ch in s:
        if ch.isspace():
            continue
        if ch == '\u201c' or ch == '\u201d':
            result.append('"')
        elif ch == '\u2018' or ch == '\u2019':
            result.append("'")
        else:
            result.append(ch)
    return "".join(result)


def _build_norm_map(text):
    norm_chars = []
    orig_indices = []
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        if ch == '\u201c' or ch == '\u201d':
            norm_chars.append('"')
            orig_indices.append(i)
        elif ch == '\u2018' or ch == '\u2019':
            norm_chars.append("'")
            orig_indices.append(i)
        else:
            norm_chars.append(ch)
            orig_indices.append(i)
    return "".join(norm_chars), orig_indices


def fuzzy_insert_comment(md_text, anchor_text, comment_content, comment_num):
    if not anchor_text or not md_text:
        return md_text, False

    norm_md, md_map = _build_norm_map(md_text)
    norm_anchor, _ = _build_norm_map(anchor_text)

    if not norm_anchor or len(norm_anchor) > len(norm_md):
        return md_text, False

    pos = norm_md.find(norm_anchor)
    if pos < 0:
        return md_text, False

    end_norm_pos = pos + len(norm_anchor) - 1
    if end_norm_pos >= len(md_map):
        return md_text, False

    orig_end_pos = md_map[end_norm_pos] + 1
    marker = f"[📝批注{comment_num}：{comment_content}]"
    new_text = md_text[:orig_end_pos] + marker + md_text[orig_end_pos:]
    return new_text, True


def parse_comments_xml(comments_xml_str):
    comments = {}
    pattern = r'<w:comment\s+[^>]*w:id="(\d+)"[^>]*>(.*?)</w:comment>'
    for match in re.finditer(pattern, comments_xml_str, re.DOTALL):
        comment_id = match.group(1)
        comment_body = match.group(2)
        texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', comment_body)
        comments[comment_id] = "".join(texts)
    return comments


def extract_comment_anchors(doc_xml_str):
    anchors = []
    start_pattern = re.compile(r'<w:commentRangeStart\s+w:id="(\d+)"\s*/>')
    end_pattern = re.compile(r'<w:commentRangeEnd\s+w:id="(\d+)"\s*/>')
    text_pattern = re.compile(r'<w:t[^>]*>([^<]*)</w:t>')

    starts = [(m.start(), m.group(1)) for m in start_pattern.finditer(doc_xml_str)]
    ends = {m.group(1): m.start() for m in end_pattern.finditer(doc_xml_str)}

    for pos, cid in starts:
        end_pos = ends.get(cid)
        if end_pos is None:
            continue
        segment = doc_xml_str[pos:end_pos]
        texts = text_pattern.findall(segment)
        anchor_text = "".join(texts)
        if anchor_text:
            anchors.append({"id": cid, "text": anchor_text})

    return anchors


def insert_comments_into_md(md_text, comments_dict, anchors_list):
    if not comments_dict or not anchors_list:
        return md_text

    result = md_text
    inserted = 0

    for anchor in anchors_list:
        cid = anchor["id"]
        anchor_text = anchor["text"]
        if cid not in comments_dict:
            continue
        if not anchor_text:
            continue

        comment_content = comments_dict[cid]
        inserted += 1

        if anchor_text in result:
            marker = f"[📝批注{inserted}：{comment_content}]"
            result = result.replace(anchor_text, anchor_text + marker, 1)
        else:
            result, ok = fuzzy_insert_comment(result, anchor_text, comment_content, inserted)
            if not ok:
                inserted -= 1

    return result


def extract_comments_to_md(docx_path, output_md_path):
    if not os.path.exists(docx_path):
        log(f"❌ 文件不存在: {docx_path}")
        return False

    if not check_pandoc():
        log("❌ Pandoc 未安装，无法转换 Word 文档")
        return False

    output_dir = os.path.dirname(output_md_path) or "."
    base_name = os.path.splitext(os.path.basename(output_md_path))[0]
    img_dir = os.path.join(output_dir, f"{base_name}_images", "media")
    os.makedirs(img_dir, exist_ok=True)

    ok = convert_with_pandoc(docx_path, output_md_path, img_dir, use_mathjax=False)
    if not ok:
        log("❌ Pandoc 转换失败")
        return False

    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            names = z.namelist()
            if 'word/comments.xml' not in names:
                log("ℹ️ 文档中没有批注，跳过批注提取")
                return True

            comments_xml = z.read('word/comments.xml').decode('utf-8')
            doc_xml = z.read('word/document.xml').decode('utf-8')
    except Exception as e:
        log(f"❌ 读取 docx 失败: {e}")
        return False

    comments_dict = parse_comments_xml(comments_xml)
    anchors = extract_comment_anchors(doc_xml)

    if not comments_dict:
        log("ℹ️ 未解析到批注内容")
        return True

    try:
        with open(output_md_path, 'r', encoding='utf-8') as f:
            md_text = f.read()
    except Exception as e:
        log(f"❌ 读取 md 失败: {e}")
        return False

    new_md = insert_comments_into_md(md_text, comments_dict, anchors)

    try:
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write(new_md)
    except Exception as e:
        log(f"❌ 写入 md 失败: {e}")
        return False

    log(f"✅ 批注提取完成，共插入 {len([a for a in anchors if a['id'] in comments_dict])} 条批注")
    return True


def insert_comments_from_docx(docx_path, md_text):
    """从 docx 文件提取批注并插入到已有的 md 文本中，返回新的 md 文本。"""
    if not os.path.exists(docx_path):
        log(f"❌ 文件不存在: {docx_path}")
        return md_text

    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            names = z.namelist()
            if 'word/comments.xml' not in names:
                log("ℹ️ 文档中没有批注")
                return md_text

            comments_xml = z.read('word/comments.xml').decode('utf-8')
            doc_xml = z.read('word/document.xml').decode('utf-8')
    except Exception as e:
        log(f"❌ 读取 docx 失败: {e}")
        return md_text

    comments_dict = parse_comments_xml(comments_xml)
    anchors = extract_comment_anchors(doc_xml)

    if not comments_dict:
        log("ℹ️ 未解析到批注内容")
        return md_text

    new_md = insert_comments_into_md(md_text, comments_dict, anchors)
    log(f"✅ 已插入 {len([a for a in anchors if a['id'] in comments_dict])} 条批注")
    return new_md
