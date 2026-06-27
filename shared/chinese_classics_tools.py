"""文言文/诗歌校对工具集 —— 文本类型识别、前置搜索、自动 diff。"""
import re
import difflib
import requests
import json

from core.logging_utils import log


CLASSICAL_PARTICLES = [
    "之", "乎", "者", "也", "矣", "焉", "哉",
    "其", "而", "于", "以", "为", "所", "耳",
    "乃", "则", "即", "皆", "凡", "诸",
    "何", "孰", "安", "焉", "胡", "奚",
    "不", "弗", "毋", "勿", "未", "非",
    "因", "故", "遂", "乃", "辄", "便",
]

# 批注标记：XML 风格 <批注 id=N><原>原文</原><改>建议</改></批注>
_ANNOTATION_RE = re.compile(r'<批注\s+id=\d+>.*?</批注>', re.DOTALL)

# 下划线/波浪线/强调标记 — 用中文全角括号
_FORMATTING_MARKER_RE = re.compile(r'【(?:波浪线|下划线|加点|/)?】|【/?[波浪线下划线加点]+】')

# Markdown 强调标记和 HTML 标签

# 试题引导语模式
_LEADIN_PATTERNS = [
    # "阅读下面的文言文，完成1-6题" — 允许批注标记插入
    re.compile(r'阅读下面的(?:文言文|古诗|唐诗|宋词|词|诗歌|元曲|散曲|文字|作品|文章|这首词|这首诗)[，。,\.、\s]*完成\d+(?:[—\-～~]\d+)?题[。]?(\[[^\]]*\])?'),
    re.compile(r'阅读下面的(?:文言文|古诗|唐诗|宋词|词|诗歌|元曲|散曲|文字|作品|文章|这首词|这首诗)[，。,\.、\s]*完成下面小?题[。]?'),
    # "二、文言文阅读（本题共4道小题，19分）" 等段落标题
    # 兼容"现代文阅读Ⅰ""文言文阅读Ⅱ"等带罗马数字/数字后缀的标题
    re.compile(r'^[\d一二三四五六七八九十]+[、，\.]\s*(?:文言文|古代诗歌|古诗词|现代文)阅读\s*[ⅠⅡⅢⅣⅤⅥ1-9一二三四五六七八九十]?[、．.]?\s*[（(][^）)]*[）)]'),
    re.compile(r'^[（(]节选自[^）)]*[）)]'),
    # Markdown 粗体标题
    re.compile(r'\*\*[\d一二三四五六七八九十]+、[^*]+\*\*'),
]


def _clean_annotations(text):
    """清理文本中的批注标记、格式标记，方便后续正则匹配。

    XML 风格标记 <批注 id=N>...</批注>，简单正则删除即可（无嵌套歧义）。
    """
    # 反复删除批注标记直到无残留（处理可能的嵌套情况）
    prev = None
    while prev != text:
        prev = text
        text = _ANNOTATION_RE.sub('', text)

    # 清理格式标记（【波浪线】等）
    text = _FORMATTING_MARKER_RE.sub('', text)
    # 清理 Markdown 强调标记（保留内部文字）
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    # 清理 HTML 标签（Pandoc 残留）
    text = re.sub(r'<[^>]+>', '', text)
    # 清理连续逗号/空白
    text = re.sub(r'[,，]{2,}', '，', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text


def _strip_leadin(text):
    """去掉试题引导语，返回正文开头的纯文本片段。"""
    # 先清理批注标记，否则会干扰引导语正则匹配
    result = _clean_annotations(text)
    for pat in _LEADIN_PATTERNS:
        result = pat.sub("", result)
    # 再去掉常见的前缀标注
    result = re.sub(r'^[\(（].*?[\)）]', '', result)
    result = re.sub(r'^[\d一二三四五六七八九十]+[、．.．]\s*', '', result)
    return result.strip()


def extract_text_start_via_api(text, api_url, api_key, model, timeout=15):
    """使用 API 从试题文本中提取文言文/诗歌正文的开头 20 字。

    用于生成精准的搜索关键词，避免引导语干扰。
    返回提取到的开头文本，失败返回 None。
    """
    # 清理批注标记，避免干扰 LLM 判断
    clean_text = _clean_annotations(text)
    sample = clean_text[:300]

    system_prompt = (
        "你是一个文本提取器。只输出 JSON，不输出任何其他内容。"
    )

    user_prompt = (
        "从以下语文试题文本中，提取文言文/古诗/词/曲的正文开头。\n"
        "\n"
        "规则：\n"
        "1. 去掉\"阅读下面的文言文，完成1-4题\"等引导语\n"
        "2. 去掉题号（如\"一、\"\"1.\"）和段落标题\n"
        "3. 去掉作者名和出处标注\n"
        "4. 只提取汉字，去掉标点符号和空格\n"
        "5. 如果文本不包含文言文或古诗词，text 填 \"MODERN\"\n"
        "\n"
        "输出格式（严格 JSON，不要其他文字）：\n"
        '{"text": "韦凑字彦宗京兆万年人永淳初解褐婺州参军事"}\n'
        "\n"
        f"文本：\n{sample}"
    )

    try:
        chat_url = api_url.rstrip("/")
        if not chat_url.endswith("/chat/completions"):
            chat_url += "/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(chat_url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
        msg = body["choices"][0].get("message", {})
        raw = msg.get("content", "") or msg.get("reasoning_content", "") or ""
        raw = raw.strip()
        log(f"   🔧 API 原始返回: {raw[:120]}")
        # 解析 JSON
        data = json.loads(raw)
        result = data.get("text", "")
        if result == "MODERN" or not result:
            return None
        # 清理结果：去标点、取前20字
        clean = re.sub(r'[^一-鿿]', '', result)
        if len(clean) > 20:
            clean = clean[:20]
        if len(clean) < 3:
            return None
        log(f"   🎯 API 提取正文开头：{clean}")
        return clean
    except Exception as e:
        log(f"   ⚠️ API 提取正文开头失败：{e}")
        return None


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
            # 额外检查：虚词密度 < 0.03 才可能是诗歌，否则是短文言文传记
            if particle_density < 0.06 and _has_poetry_markers(clean_text):
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
        # 额外检查：文言文散文（而非诗歌）的虚词密度通常 >= 0.03
        # 避免把短篇文言文传记（如韦凑传开头）误判为诗歌
        if _particle_density(text) < 0.06:
            return True
        # 如果虚词密度达到文言文水平，则不是诗歌
        return False

    return False


def _is_classical(clean_text, particle_density=None):
    if len(clean_text) < 10:
        return False

    if particle_density is None:
        density = _particle_density(clean_text)
    else:
        # 可能来自 detect_text_type 的含标点版本，重新计算以确保准确性
        density = _particle_density(clean_text) if particle_density < 0.04 and len(clean_text) > 50 else particle_density

    if density >= 0.08:
        return True

    classical_markers = ["曰", "云", "言", "谓", "对曰", "问曰", "先生",
                         "寡人", "陛下", "大王", "诸侯", "大夫",
                         "之", "乎", "也", "矣", "焉", "哉"]
    marker_count = 0
    for m in classical_markers:
        if m in clean_text:
            marker_count += 1

    # 长文本要求更高的虚词密度（避免现代文引用古文时被误判）
    if len(clean_text) > 500:
        if density >= 0.07 and marker_count >= 5:
            return True
    elif density >= 0.06 and marker_count >= 4:
        return True

    # 回退：出现「字+X」人名模式 + 官职关键词
    if density >= 0.035:
        has_name = re.search(r'[一-鿿]{1,4}字[一-鿿]{1,4}', clean_text)
        has_title = re.search(r'(刺史|司马|长史|司农|法曹|参军事|太府|通事舍人|太守|县令|尚书|侍郎|御史|大理|鸿胪)', clean_text)
        if has_name and (marker_count >= 1 or has_title):
            # 现代文阅读题(含古人名引用)误入回退分支的否决：真正文言文题不会带这些标记词。
            # 仅作用于低密度回退分支，不影响密度≥0.08 等高密度主分支。
            modern_markers = ("现代文阅读", "论述类", "实用类", "文学类",
                              "非连续性文本", "信息类", "阅读下面的文字")
            if any(m in clean_text for m in modern_markers):
                return False
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


def extract_excerpt_from_full(full_text, excerpt_text, margin=20):
    """从识典全文(full_text)中，截取出与节选(excerpt_text)对应的区间。

    用 difflib 对齐全文与节选（去标点版），保留匹配区间的两端各 margin 字。
    可多不可少——确保不因为截断而漏掉节选边缘文字。

    Args:
        full_text: 识典古籍全文（带标点）
        excerpt_text: 试卷节选文本（带标点）
        margin: 两端各保留的额外字数，默认 20

    Returns:
        str: 截取后的原文区间，或 None（节选在全文找不到匹配时）
    """
    if not full_text or not excerpt_text:
        return None

    def _norm(s):
        return re.sub(r'[^一-鿿]', '', s)

    n_full = _norm(full_text)
    n_excerpt = _norm(excerpt_text)

    if len(n_excerpt) == 0 or len(n_full) == 0:
        return None

    matcher = difflib.SequenceMatcher(None, n_full, n_excerpt)
    blocks = matcher.get_matching_blocks()

    real_blocks = [b for b in blocks if b.size > 0]
    if not real_blocks:
        return None

    first_start = real_blocks[0].a
    last_end = real_blocks[-1].a + real_blocks[-1].size

    start = max(0, first_start - margin)
    end = min(len(n_full), last_end + margin)

    # 映射去标点位置 → 原始带标点位置
    chi_pos = 0
    full_start = full_end = 0
    for i, ch in enumerate(full_text):
        if full_start == 0 and chi_pos == start:
            full_start = i
        if chi_pos == end:
            full_end = i
            break
        if '一' <= ch <= '鿿':
            chi_pos += 1
    else:
        full_end = len(full_text)

    return full_text[full_start:full_end]


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
        lines.append("> **指令**：该段文言文/诗歌的原文已通过识典古籍/搜韵网自动验证，")
        lines.append("> 与权威原文字面完全一致，无需再对正文内容进行逐字校对。")
        lines.append("> 请仅检查：标点符号、注释编号、格式标记是否与原文匹配。")
    lines.append("")

    # 硬性约束：前置搜索已提供权威原文+差异列表时，禁止 LLM 重复检索同段原文。
    # 位于 user 消息顶部，以与 config 同强度的「严禁/不得」压制 system 层「必须用工具」，
    # 避免 LLM 在前置搜索成功后仍反复调 web_search/web_fetch 搜同一原文。
    lines.append("---")
    lines.append("")
    lines.append("⚠️ **硬性约束**：本段原文已由程序自动从识典古籍/搜韵网检索并完成字面比对，")
    lines.append("权威原文与差异列表均已在上方给出。**严禁再使用 web_search 或 web_fetch 检索本段文言文/诗歌的原文**，")
    lines.append("仅需基于上方「权威原文」与「字面差异」逐条判断即可。")
    lines.append("如需验证典故出处、作者生平、字词释义等前置未覆盖的信息，可按需搜索，但不得搜索本段原文本身。")
    lines.append("")

    return "\n".join(lines)


def search_original_text(text_type, sample_text):
    """搜索权威原文。

    策略：识典古籍(文言文, Playwright) → 搜韵网(诗歌) → ddgs/百度搜索 → 提取原文。
    Playwright 不可用时自动回退到搜索引擎方案。

    Args:
        text_type: 'classical' | 'poetry' | 'modern'
        sample_text: 待搜索的关键词（应尽量是正文而非引导语）
    """
    if text_type == "modern":
        return None
    if not sample_text or not sample_text.strip():
        return None

    sample = sample_text.strip()
    sample = _strip_leadin(sample)
    sample = re.sub(r'[#*`\[\]()\s]', '', sample)
    if len(sample) > 10:
        sample = sample[:10]
    if len(sample) < 4:
        return None

    log(f"   🔍 搜索关键词: {sample}")

    try:
        from shared.web_tools import WebFetchTool, WebSearchTool
        import urllib.parse

        fetcher = WebFetchTool()
        searcher = WebSearchTool()

        # 第1优先：识典古籍（文言文，Playwright 可用时）
        if text_type == "classical":
            try:
                from shared.shidianguji_playwright import is_playwright_available, search_and_extract
                # 只在 Playwright 可用时才尝试识典
                if is_playwright_available():
                    log(f"   📚 尝试识典古籍搜索...")
                    sdg_result = search_and_extract(sample)
                    if sdg_result and len(sdg_result) > 50:
                        log(f"   ✅ 识典古籍找到原文 ({len(sdg_result)} 字)")
                        return sdg_result
                    log(f"   ⚠️ 识典古籍未找到或结果过短")
            except Exception as e:
                log(f"   ⚠️ 识典古籍搜索异常: {e}")

        # 第2优先：搜韵网（仅诗歌）
        if text_type == "poetry":
            url = f"https://sou-yun.cn/QueryPoem.aspx?q={urllib.parse.quote(sample)}"
            result = fetcher._run(url)
            if result and not result.startswith("[") and "搜索结果为空" not in result:
                log(f"   ✅ 搜韵网找到结果")
                return _extract_first_poem(result)
            log(f"   ⚠️ 搜韵网未找到，尝试百度搜索...")

        # 第3优先：DuckDuckGo/Baidu 搜索 + 抓取
        search_query = f"{sample} 原文"
        log(f"   🌐 搜索: {search_query[:40]}...")
        # 先尝试 ddgs（返回直接 URL），失败回退百度
        search_result = None
        for backend in ["ddgs", "baidu"]:
            try:
                search_result = searcher._run(search_query, backend=backend)
                if search_result and not search_result.startswith("[E"):
                    break
            except Exception:
                continue

        if search_result:
            try:
                items = json.loads(search_result)
                for item in items:
                    url = item.get("url", "")
                    if not url:
                        continue
                    # 跳过百度文库（403 反爬）
                    if "wenku.baidu.com" in url:
                        continue

                    log(f"   📄 尝试抓取: {item.get('title', '')[:50]}")
                    page = fetcher._run(url)
                    if page and len(page) > 200 and not page.startswith("["):
                        # 提取页面中的文言文/诗歌部分
                        if text_type == "poetry":
                            extracted = _extract_first_poem(page)
                        else:
                            extracted = _extract_first_classical(page)
                        if extracted and len(extracted) > 30:
                            log(f"   ✅ 搜索→抓取成功 ({len(extracted)} 字)")
                            return extracted
                        else:
                            log(f"   ⚠️ 页面未提取到足够文本（{len(extracted) if extracted else 0} 字）")
            except (json.JSONDecodeError, Exception) as e:
                log(f"   ⚠️ 搜索结果解析失败: {e}")

        log(f"   ⚠️ 搜索未找到可用原文")

    except Exception as e:
        log(f"   ⚠️ 前置搜索异常: {e}")

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
    """从网页文本中提取文言文正文。跳过导航、页眉等噪音。"""
    if not text:
        return None
    lines = text.strip().splitlines()
    result_lines = []
    started = False

    for line in lines:
        stripped = line.strip()
        # 跳过明显非正文的行
        if not stripped:
            continue
        if stripped.startswith("【") or stripped.startswith("##"):
            continue
        if len(stripped) < 6:
            continue
        # 跳过纯导航/链接行（含大量空格或特殊字符少的中文）
        chinese = re.findall(r'[一-鿿]', stripped)
        if len(chinese) < 4:
            continue

        # 检测"正文开始"信号：出现高密度文言虚词或连续中文
        density = _particle_density(''.join(chinese)) if chinese else 0
        if not started:
            if density >= 0.03 or len(chinese) >= 15:
                started = True
            else:
                continue

        result_lines.append(stripped)
        if len(result_lines) >= 40:
            break

    if len(result_lines) >= 3:
        return "\n".join(result_lines)
    return None


def preprocess_for_proofread(md_text, api_url=None, api_key=None, model=None):
    """前置处理：检测文本类型 → 搜索权威原文 → diff → 注入参考资料。

    Args:
        md_text: 待校对的 Markdown 文本（含格式标记）
        api_url/api_key/model: 可选的 API 配置，用于精准提取搜索关键词

    搜索关键词取前 10 个汉字。识典古籍 Playwright 优先，失败回退 ddgs。
    """
    if not md_text or not md_text.strip():
        return md_text

    text_type = detect_text_type(md_text)

    if text_type == "modern":
        return md_text

    log(f"   📖 检测到文本类型: {'文言文' if text_type == 'classical' else '诗歌'}，启动前置搜索...")

    # 步骤1：生成搜索关键词（正则去除引导语后取前 10 汉字）
    search_key = None

    from shared.docx_format_enhancer import strip_format_markers
    clean = _clean_annotations(md_text)
    clean = strip_format_markers(clean)
    clean = re.sub(r'[#*`\[\]()]', '', clean)
    clean = re.sub(r'\s+', '', clean)
    clean = re.sub(r'^第\d+题[：:.,，。、\s]*', '', clean)
    search_key = _strip_leadin(clean)
    if len(search_key) > 10:
        search_key = search_key[:10]
    log(f"   📝 回退正则提取关键词: {search_key}")

    # 步骤2：去权威来源搜索原文
    original = search_original_text(text_type, search_key)

    if original is None:
        log(f"   ⚠️ 未找到权威原文，跳过前置 diff")
        return md_text

    # 步骤3：从全文截取节选范围（可多不可少），再做字符级 diff
    original_excerpt = extract_excerpt_from_full(original, md_text, margin=20)
    if original_excerpt:
        log(f"   ✂️ 从全文({len(original)}字)中截取节选范围({len(original_excerpt)}字)")
        original = original_excerpt

    clean_given = re.sub(r'[#*`\[\]()\s]', '', md_text)
    clean_orig = re.sub(r'[#*`\[\]()\s]', '', original)

    diff_result = diff_characters(clean_orig, clean_given)
    reference = build_reference_section(text_type, original, diff_result["differences"])

    if diff_result["identical"]:
        log(f"   ✅ 前置校验完成：原文一致，无需 LLM 额外搜索")
    else:
        log(f"   ⚡ 发现 {len(diff_result['differences'])} 处字面差异，已注入 prompt 供 LLM 判断")

    return reference + "\n---\n\n" + md_text
