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

INLINE_MARKER_DETECT_RE = re.compile(r'【\d+\|.*\|[^】]*】')
"""检测是否存在内联校对标记 【N|原文|改为】。用于 parsing.py / format_enforcement.py。"""

INLINE_MARKER_CAPTURE_RE = re.compile(r'【([\d①-⑳]+)\|([^|]*?)\|([^】]*?)】')
"""提取内联校对标记的三个字段（编号、原文、改为）。用于 latex_generator.py。

注意：编号支持阿拉伯数字 1-99 和带圈数字 ①-⑳，原文和改为字段为非贪婪匹配。
"""
