import os, re, json


def _circle_to_int(ch: str) -> int | None:
    code = ord(ch)
    if 0x2460 <= code <= 0x2473:
        return code - 0x2460 + 1
    return None


def _parse_marker_num(s: str) -> int:
    n = _circle_to_int(s[0])
    if n is not None:
        return n
    return int(s)


def _parse_inline_format(text: str, summary: str) -> dict | None:
    m = re.search(r'\n###\s*修改原因\s*\n', text)
    if not m:
        return None
    marked_section = text[:m.start()]
    reasons_section = text[m.end():]

    marker_pos = re.search(r'^###\s*标记原文\s*\n?', marked_section, re.MULTILINE)
    if marker_pos:
        marked_section = marked_section[marker_pos.end():]

    marked_section = re.sub(r'^编号：.+\n?', '', marked_section)
    marked_section = re.sub(r'^内容：\n?', '', marked_section)

    reasons_section = re.split(r'\n###\s', reasons_section)[0]
    reasons = {}
    pattern_circled = r'([①-⑳](?:-([①-⑳]))?)\s*(.+?)(?=\n[①-⑳]|\n\d+[\.\)]|\n\n|\Z)'
    if re.search(r'(?:^|\n)[①-⑳]', reasons_section):
        for rm in re.finditer(pattern_circled, reasons_section, re.DOTALL):
            sn = _circle_to_int(rm.group(1)[0])
            en = _circle_to_int(rm.group(2)) if rm.group(2) else sn
            rt = rm.group(3).strip()
            for n in range(sn, (en or sn) + 1):
                reasons[n] = rt
    else:
        pattern_ascii = r'(\d+)(?:\s*[-–]\s*(\d+))?\s*[\.\)\s]\s*(.+?)(?=\n\d+[\.\)\s]|\n\n|\Z)'
        for rm in re.finditer(pattern_ascii, reasons_section, re.DOTALL):
            sn = int(rm.group(1))
            en = int(rm.group(2)) if rm.group(2) else sn
            rt = rm.group(3).strip()
            if not rt:
                continue
            for n in range(sn, en + 1):
                reasons[n] = rt

    corrections = []
    seen_nums = set()

    def _extract(marker):
        num = _parse_marker_num(marker.group(1))
        orig = marker.group(2)
        corr = marker.group(3).strip() if marker.group(3) else ""
        if num not in seen_nums:
            seen_nums.add(num)
            corrections.append({
                "num": num,
                "type": "text",
                "original": orig,
                "correction": corr,
                "reason": reasons.get(num, ""),
            })
        return ""

    _clean_marked = re.sub(r'【(\d+)\|([^|]*?)\|([^】]*?)】', _extract, marked_section)
    corrections.sort(key=lambda x: x.get("num", 0))

    if not summary and not corrections:
        return None
    return {
        "corrections": corrections,
        "summary": summary or "无问题",
        "marked_text": marked_section.replace('\n', '\\n'),
    }


def _parse_old_format(text: str, summary: str) -> dict | None:
    blocks = re.split(r"\n?(?:###+\s*修改\s*\d+)\s*\n", text)
    corrections = []
    for block in blocks[1:]:
        corr = {}
        cur_field = None
        cur_val = []
        for line in block.strip().split("\n"):
            s = line.strip()
            matched = False
            for prefix, field in [("- **类型**:", "type"), ("- **原文**:", "original"),
                                   ("- **改为**:", "correction"), ("- **原因**:", "reason"),
                                   ("- **位置**:", "location")]:
                if s.startswith(prefix):
                    if cur_field and cur_val:
                        v = "\n".join(cur_val)
                        if cur_field in ("original", "correction", "location"):
                            m = re.search(r"``(.+?)``", v) or re.search(r"`([^`]+)`", v)
                            corr[cur_field] = m.group(1) if m else v
                        else:
                            corr[cur_field] = v
                    cur_field = field
                    cur_val = [s.split(":", 1)[1].strip() if ":" in s else ""]
                    matched = True
                    break
            if not matched and cur_field:
                cur_val.append(s)
        if cur_field and cur_val:
            v = "\n".join(cur_val)
            if cur_field in ("original", "correction", "location"):
                m = re.search(r"``(.+?)``", v) or re.search(r"`([^`]+)`", v)
                corr[cur_field] = m.group(1) if m else v
            else:
                corr[cur_field] = v
        if corr.get("original") or corr.get("location"):
            corr.setdefault("type", "text")
            corr.setdefault("correction", "")
            corr.setdefault("reason", "")
            corrections.append(corr)
    if not summary and not corrections:
        return None
    return {"corrections": corrections, "summary": summary or "无问题"}


def parse_proofread_md(text: str):
    if not text or not text.strip():
        return None
    text = text.strip()
    summary = ""
    for kw in ["严重错误", "一般问题", "轻微问题", "无问题"]:
        if kw in text:
            summary = kw
            break

    if "### 标记原文" in text and re.search(r'【\d+\|.*\|[^】]*】', text):
        result = _parse_inline_format(text, summary)
        if result:
            return result

    return _parse_old_format(text, summary)


def extract_json(text: str):
    return parse_proofread_md(text)


def save_proofread_json(res: str, q_dir: str, tool_calls: list | None = None):
    data = extract_json(res)
    if data is None:
        return False
    if tool_calls:
        data["tool_calls"] = tool_calls
    json_path = os.path.join(q_dir, "_校对数据.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
