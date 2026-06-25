"""文言文/诗歌校对工具集 —— 文本类型识别、前置搜索、自动 diff。"""
import re
import difflib


CLASSICAL_PARTICLES = [
    "之", "乎", "者", "也", "矣", "焉", "哉",
    "其", "而", "于", "以", "为", "所", "耳",
    "乃", "则", "即", "皆", "凡", "诸",
    "何", "孰", "安", "焉", "胡", "奚",
    "不", "弗", "毋", "勿", "未", "非",
    "因", "故", "遂", "乃", "辄", "便",
]


def detect_text_type(text):
    if not text or not text.strip():
        return "modern"

    clean = re.sub(r'\s+', '', text)
    if len(clean) < 5:
        return "modern"

    lines = [re.sub(r'[^\u4e00-\u9fff]', '', l.strip())
             for l in text.splitlines() if l.strip()]
    lines = [l for l in lines if l]

    particle_density = _particle_density(clean)

    if particle_density >= 0.12 and len(clean) < 50:
        return "classical"

    if _is_poetry(lines, clean, particle_density):
        return "poetry"

    if _is_classical(clean, particle_density):
        return "classical"

    return "modern"


def _particle_density(clean_text):
    if not clean_text:
        return 0
    count = 0
    for p in CLASSICAL_PARTICLES:
        count += clean_text.count(p)
    return count / len(clean_text)


def _is_poetry(lines, clean_text, particle_density=0):
    chinese_lines = [l for l in lines if len(l) >= 3]
    if not chinese_lines:
        return False

    if particle_density >= 0.15:
        return False

    lengths = [len(l) for l in chinese_lines[:10]]
    if not lengths:
        return False

    avg_len = sum(lengths) / len(lengths)
    variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
    std_dev = variance ** 0.5

    five_char = sum(1 for l in lengths if l == 5)
    seven_char = sum(1 for l in lengths if l == 7)
    ten_char = sum(1 for l in lengths if l == 10)
    fourteen_char = sum(1 for l in lengths if l == 14)
    total = len(lengths)

    if total >= 2:
        if five_char >= total * 0.6:
            return True
        if seven_char >= total * 0.6:
            return True
        if ten_char >= total * 0.6:
            return True
        if fourteen_char >= total * 0.6:
            return True
        if std_dev <= 1.5 and 4 <= avg_len <= 15:
            return True

    if total == 1:
        l = lengths[0]
        if l in [20, 28, 40, 56]:
            if _has_poetry_markers(clean_text):
                return True
        if l >= 8 and l <= 60:
            if _is_clear_poetry_line(clean_text):
                return True

    return False


def _has_poetry_markers(text):
    markers = ["。", "，", "、", "；", "？", "！"]
    count = sum(text.count(m) for m in markers)
    if len(text) > 0 and count / len(text) > 0.05:
        return True
    return False


def _is_clear_poetry_line(text):
    clean = re.sub(r'[^\u4e00-\u9fff]', '', text)
    if len(clean) < 8:
        return False

    segments = re.split(r'[，。；？！、]', text)
    segments = [re.sub(r'[^\u4e00-\u9fff]', '', s) for s in segments]
    segments = [s for s in segments if s]

    if len(segments) < 4:
        return False

    seg_lens = [len(s) for s in segments]
    avg = sum(seg_lens) / len(seg_lens)
    if avg < 4 or avg > 8:
        return False

    variance = sum((l - avg) ** 2 for l in seg_lens) / len(seg_lens)
    std_dev = variance ** 0.5

    if std_dev <= 1.0:
        return True

    return False


def _is_classical(clean_text, particle_density=None):
    if len(clean_text) < 10:
        return False

    if particle_density is None:
        density = _particle_density(clean_text)
    else:
        density = particle_density

    if density >= 0.08:
        return True

    classical_markers = ["曰", "云", "言", "谓", "对曰", "问曰", "先生",
                         "寡人", "陛下", "大王", "诸侯", "大夫",
                         "之", "乎", "也", "矣", "焉", "哉"]
    marker_count = 0
    for m in classical_markers:
        if m in clean_text:
            marker_count += 1

    if density >= 0.05 and marker_count >= 3:
        return True

    return False


def diff_characters(original, given):
    if not original and not given:
        return {"identical": True, "differences": []}
    if not original or not given:
        return {
            "identical": False,
            "differences": [{"original": original or "(空)", "given": given or "(空)", "position": 0, "type": "replace"}]
        }

    orig_chars = list(original)
    given_chars = list(given)

    s = difflib.SequenceMatcher(None, orig_chars, given_chars)
    diffs = []

    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if tag == 'equal':
            continue
        orig_part = "".join(orig_chars[i1:i2])
        given_part = "".join(given_chars[j1:j2])
        diffs.append({
            "position": i1,
            "original": orig_part,
            "given": given_part,
            "type": tag,
        })

    return {
        "identical": len(diffs) == 0,
        "differences": diffs,
    }


def build_reference_section(text_type, original, diffs):
    type_label = {
        "classical": "文言文",
        "poetry": "诗歌",
    }.get(text_type, "文本")

    lines = [f"## 前置参考：{type_label}原文校验", ""]

    if original:
        lines.append("### 权威原文（来自识典古籍/搜韵网）")
        lines.append("")
        lines.append("> " + original.replace("\n", "\n> "))
        lines.append("")
    else:
        lines.append("### 权威原文")
        lines.append("")
        lines.append("> 未能检索到权威原文，请结合上下文判断。")
        lines.append("")
        return "\n".join(lines)

    if diffs and len(diffs) > 0:
        lines.append("### 字面差异（自动比对）")
        lines.append("")
        for i, d in enumerate(diffs, 1):
            dtype = d.get("type", "replace")
            orig = d.get("original", "")
            giv = d.get("given", "")
            pos = d.get("position", 0)
            if dtype == "replace":
                lines.append(f"{i}. 第{pos}位：「{orig}」→「{giv}」（替换）")
            elif dtype == "delete":
                lines.append(f"{i}. 第{pos}位：「{orig}」（原文有，待校稿缺失）")
            elif dtype == "insert":
                lines.append(f"{i}. 第{pos}位：「{giv}」（待校稿多出）")
            else:
                lines.append(f"{i}. 第{pos}位：{orig} → {giv}")
        lines.append("")
        lines.append("⚠️ 以上差异为程序自动比对结果，请结合语境判断是否为真正的错误。")
    else:
        lines.append("### 比对结果")
        lines.append("")
        lines.append("✅ 待校稿与权威原文字面一致。")
    lines.append("")

    return "\n".join(lines)


def search_original_text(text_type, sample_text):
    if text_type == "modern":
        return None
    if not sample_text or not sample_text.strip():
        return None

    sample = sample_text.strip()
    if len(sample) > 50:
        sample = sample[:50]

    try:
        from shared.web_tools import WebFetchTool
        fetcher = WebFetchTool()

        if text_type == "poetry":
            import urllib.parse
            url = f"https://sou-yun.cn/QueryPoem.aspx?q={urllib.parse.quote(sample)}"
            result = fetcher._run(url)
            if result and not result.startswith("[") and "搜索结果为空" not in result:
                return _extract_first_poem(result)

        if text_type == "classical" or text_type == "poetry":
            import urllib.parse
            url = f"https://www.shidianguji.com/search/{urllib.parse.quote(sample)}"
            result = fetcher._run(url)
            if result and not result.startswith("[") and "未收录" not in result and "为空" not in result:
                return _extract_first_classical(result)

    except Exception:
        pass

    return None


def _extract_first_poem(text):
    if not text:
        return None
    lines = text.strip().splitlines()
    poem_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("【") or stripped.startswith("##") or stripped.startswith("#"):
            continue
        if stripped:
            poem_lines.append(stripped)
        if len(poem_lines) >= 20:
            break
    if poem_lines:
        return "\n".join(poem_lines)
    return None


def _extract_first_classical(text):
    if not text:
        return None
    lines = text.strip().splitlines()
    result_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("【") or stripped.startswith("##"):
            continue
        if stripped:
            result_lines.append(stripped)
        if len(result_lines) >= 30:
            break
    if result_lines:
        return "\n".join(result_lines)
    return None


def preprocess_for_proofread(md_text):
    if not md_text or not md_text.strip():
        return md_text

    text_type = detect_text_type(md_text)

    if text_type == "modern":
        return md_text

    sample = re.sub(r'[#*`\[\]()]', '', md_text)
    sample = re.sub(r'\s+', '', sample)
    if len(sample) > 100:
        sample = sample[:100]

    original = search_original_text(text_type, sample)

    if original is None:
        return md_text

    clean_given = re.sub(r'[#*`\[\]()\s]', '', md_text)
    clean_orig = re.sub(r'[#*`\[\]()\s]', '', original)

    diff_result = diff_characters(clean_orig, clean_given)
    reference = build_reference_section(text_type, original, diff_result["differences"])

    return reference + "\n---\n\n" + md_text
