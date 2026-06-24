import os, subprocess
from core.logging_utils import log

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
    cmd = [
        pandoc, "-f", "docx", "-t", "markdown",
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
