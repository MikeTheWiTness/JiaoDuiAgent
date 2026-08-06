import os
import subprocess

from core.logging_utils import log


def enhance_docx_conversion(docx_path, output_md):
    """增强 Word 文档转换，补充 Pandoc 丢失的格式。

    用 python-docx 提取着重号、波浪线、下划线等特殊格式，
    在 Markdown 中用自定义标记保留。

    Args:
        docx_path: 原始 Word 文档路径
        output_md: Pandoc 转换后的 Markdown 文件路径

    Returns:
        bool: 是否成功增强
    """
    try:
        from shared.docx_format_enhancer import inject_format_markers
    except ImportError:
        return False

    try:
        with open(output_md, encoding='utf-8') as f:
            md_text = f.read()

        enhanced = inject_format_markers(md_text, docx_path)

        with open(output_md, 'w', encoding='utf-8') as f:
            f.write(enhanced)

        return True
    except Exception as e:
        log(f"⚠️ 格式增强失败: {e}")
        return False

PANDOC_PATH = None


def find_pandoc():
    global PANDOC_PATH
    if PANDOC_PATH:
        return PANDOC_PATH
    import sys
    if getattr(sys, 'frozen', False):
        local = os.path.join(os.path.dirname(sys.executable), "pandoc.exe")
        if os.path.exists(local):
            PANDOC_PATH = local
            return PANDOC_PATH
    PANDOC_PATH = "pandoc"
    return PANDOC_PATH


def check_pandoc():
    pandoc = find_pandoc()
    try:
        r = subprocess.run([pandoc, "--version"], capture_output=True, text=True,
                           **(dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}))
        if r.returncode == 0:
            log(f"✅ Pandoc: {r.stdout.splitlines()[0]}")
            return True
    except FileNotFoundError:
        log("❌ Pandoc 未安装")
    return False


def convert_with_pandoc(input_path, output_md, img_dir, use_mathjax=False):
    pandoc = find_pandoc()
    # -t markdown-smart: 禁用 pandoc 的“智能引号”扩展，
    # 防止中文弯引号 "" 被转换为英文直引号 ""
    cmd = [
        pandoc, "-f", "docx", "-t", "markdown-smart",
        "--extract-media", img_dir, "--wrap", "none",
        "--markdown-headings", "atx",
    ]
    if use_mathjax:
        cmd.insert(3, "--mathjax")
    cmd.extend([input_path, "-o", output_md])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           **(dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}))
        return r.returncode == 0
    except Exception as e:
        log(f"   Pandoc 异常: {e}")
        return False
