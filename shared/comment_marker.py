"""批注与内联校对标记的正则定义（单一源，三处使用点各保留语义差异）。

三处标记语义不同，仅集中定义避免散落副本：
1. docx 批注结束令牌：CMTEND{N}Z 占位符替换
2. XML 批注：<批注 id=N><原>...</原><改>...</改></批注>
3. 内联校对标记：检测用 _DETECT_RE vs 提取用 _CAPTURE_RE
"""
import re

# ---- 1. Word 批注结束令牌（docx_comments.py 使用） ----

COMMENT_END_TOKEN_RE = re.compile(r'CMTEND(\d+)Z')
"""匹配 Word 批注占位符 CMTEND{N}Z，用于精确还原批注到原文。"""

# ---- 2. XML 批注标记（latex_generator.py 使用） ----

XML_ANNOTATION_RE = re.compile(
    r'<批注\s+id=(\d+)><原>(.*?)</原><改>(.*?)</改></批注>'
)
"""匹配 XML 格式批注标记，含原文字段和修改字段。"""

# ---- 3. 内联校对标记 ----

INLINE_MARKER_CAPTURE_RE = re.compile(
    r'【(\d+)\|((?:\\\||[^|])*)\|([^】]*?)】', re.DOTALL)
"""提取内联校对标记的三个字段（编号、原文、改为）。

parsing.py / docx_report.py / latex_generator.py 共用单一源。
编号为阿拉伯数字；原文字段支持 LaTeX 转义竖线；re.DOTALL 支持跨行标记。
"""

INLINE_MARKER_DETECT_RE = INLINE_MARKER_CAPTURE_RE
"""检测是否存在内联校对标记（与 CAPTURE 同源，带 DOTALL 支持跨行）。用于 parsing.py / format_enforcement.py。"""


_MARKER_MASK_RE = re.compile(r"【\d+\|[^】]*】")
"""屏蔽用：匹配整个内联标记 【N|原文|改为】，扫描公式时替换为等长无 $ 占位。"""


def scan_math_spans(text: str) -> list[tuple[int, int]]:
    """扫描行内公式 `$...$` 的 [start, end) 区间列表（每行内成对配对）。

    返回全文偏移（累计行偏移），与 re.Match.start() 对齐。
    `\\$`（转义美元）不参与配对；标记字段内部的 `$`（如 `【1|a$|b$】`）
    先屏蔽为等长占位，避免干扰公式配对。
    用于检测批注锚点/内联标记是否落在公式内部。
    """
    masked = _MARKER_MASK_RE.sub(
        lambda m: "【" + "X" * (len(m.group(0)) - 2) + "】", text)
    spans = []
    offset = 0
    for line in masked.split("\n"):
        start = None
        for i, ch in enumerate(line):
            if ch != "$" or (i > 0 and line[i - 1] == "\\"):
                continue
            if start is None:
                start = offset + i
            else:
                spans.append((start, offset + i + 1))
                start = None
        offset += len(line) + 1
    return spans
