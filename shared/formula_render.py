"""LaTeX 公式 → PNG 渲染（matplotlib mathtext，Word 批注插图用）。

字体策略（动态切换）：
- 无中文字符的公式 → 纯 STIX fontset：变量斜体衬线（Times 风格）
- 含中文字符的公式 → custom fontset：
  - 裸中文字符预处理包进 `\\mathrm{...}` → rm 字体（系统 CJK 宋体）渲染
  - 拉丁变量走 it 字体（STIXGeneral 斜体）——中文公式里变量保持斜体
  - STIX fallback 兜底数学符号
- 无系统 CJK 字体且公式含中文 → 拒绝渲染（调用方降级为纯文本）
- 矩阵/多行公式等 mathtext 不支持的结构抛异常，同样拒绝
"""

import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")

# 中文字体候选：衬线（宋体）优先，黑体兜底
_CJK_CANDIDATES = [
    "STSong", "Songti SC", "SimSun", "NSimSun",
    "Noto Serif CJK SC", "Source Han Serif SC",
    "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
    "Source Han Sans SC", "WenQuanYi Zen Hei",
]

# 纯 STIX 配置（普通公式：斜体衬线）
_STIX_RC = {
    "mathtext.fontset": "stix",
    "font.family": "STIXGeneral",
}

# 含中文公式配置：rm=系统 CJK 字体（\mathrm/文本），it=STIX 斜体（变量）
# 注意：mathtext custom 走 UnicodeFonts，findfont 不带 style，必须用
# "字体名:italic" 语法显式指定斜体变体，否则变量渲染为正体
_CJK_RC = {
    "mathtext.fontset": "custom",
    "mathtext.rm": None,
    "mathtext.it": "STIXGeneral:italic",
    "mathtext.bf": "STIXGeneral:weight=bold",
    "mathtext.cal": "STIXGeneral",
    "mathtext.tt": "STIXGeneral",
    "mathtext.fallback": "stix",
    "font.family": ["STIXGeneral", None],
}


def _find_cjk_font() -> str | None:
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in _CJK_CANDIDATES:
        if cand in names:
            return cand
    return None


_CJK_FONT = _find_cjk_font()
if _CJK_FONT:
    _CJK_RC["mathtext.rm"] = _CJK_FONT
    _CJK_RC["font.family"] = ["STIXGeneral", _CJK_FONT]


def _wrap_bare_cjk(latex_body: str) -> str:
    """把公式中裸中文字符包进 \\mathrm{...}（rm 字体渲染）。

    已在 \\text{...} / \\mathrm{...} 内的中文保持不动，避免嵌套。
    """
    placeholders = {}

    def _protect(m):
        key = f"\x00{len(placeholders)}\x00"
        placeholders[key] = m.group(0)
        return key

    body = re.sub(r"\\text\{[^}]*\}|\\mathrm\{[^}]*\}", _protect, latex_body)
    body = _CJK_RUN_RE.sub(lambda m: r"\mathrm{" + m.group(0) + "}", body)
    for key, value in placeholders.items():
        body = body.replace(key, value)
    return body


def latex_to_png(latex_body: str, out_path, fontsize: float = 14, dpi: int = 200) -> bool:
    """渲染 LaTeX 公式体（不含 $ 包裹）为透明 PNG，成功返回 True。

    无系统 CJK 字体且公式含中文字符时返回 False；渲染抛异常时返回 False
    并清理可能残留的输出文件。
    """
    if not latex_body:
        return False
    has_cjk = bool(_CJK_RE.search(latex_body))
    if _CJK_FONT is None and has_cjk:
        return False
    if has_cjk:
        latex_body = _wrap_bare_cjk(latex_body)
    rc = _CJK_RC if has_cjk else _STIX_RC
    try:
        with plt.rc_context(rc):
            fig = plt.figure(figsize=(0.1, 0.1))
            fig.text(0, 0, f"${latex_body}$", fontsize=fontsize)
            fig.savefig(out_path, dpi=dpi, transparent=True,
                        bbox_inches="tight", pad_inches=0.02)
            plt.close(fig)
        return True
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        try:
            os.remove(out_path)
        except OSError:
            pass
        return False
