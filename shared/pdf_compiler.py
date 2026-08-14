"""
LaTeX → PDF 编译模块
调用 xelatex 编译 .tex 文件，处理错误和清理辅助文件。

xelatex 查找优先级：
1. XELATEX_PATH 环境变量（显式覆盖）
2. 系统 PATH 上的 xelatex（已安装 TeX Live / MiKTeX）
3. 内嵌便携版（PyInstaller 打包时随 exe 分发）
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

# 模块级缓存：已发现的 xelatex 路径
_XELATEX_PATH = None

# xelatex 编译超时（秒）
LATEX_COMPILE_TIMEOUT = 120


def _find_bundled_xelatex(exe_dir: str) -> str | None:
    """在内嵌便携 TeX 发行版中查找 xelatex.exe。

    PyInstaller v5.x: 数据在 exe 同级的 texlive/bin/windows/xelatex.exe
    PyInstaller v6.x: 数据在 exe_dir/_internal/texlive/bin/windows/xelatex.exe
    """
    candidates = [
        os.path.join(exe_dir, "_internal", "texlive", "bin", "windows", "xelatex.exe"),
        os.path.join(exe_dir, "texlive", "bin", "windows", "xelatex.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _find_xelatex() -> str:
    """定位 xelatex.exe，缓存结果。

    优先级：环境变量 > 内嵌便携版 > 系统 PATH
    打包后优先使用内嵌版，避免系统 LaTeX 版本/配置不兼容。
    """
    global _XELATEX_PATH
    if _XELATEX_PATH is not None:
        return _XELATEX_PATH

    # 1. 显式环境变量（用户明确指定）
    env_path = os.environ.get("XELATEX_PATH")
    if env_path and os.path.isfile(env_path):
        _XELATEX_PATH = env_path
        return _XELATEX_PATH

    # 2. 内嵌便携版（打包后优先，确保版本一致）
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        bundled = _find_bundled_xelatex(exe_dir)
        if bundled:
            _XELATEX_PATH = bundled
            return _XELATEX_PATH

    # 3. 系统 PATH（开发时或便携版不可用时）
    system_xelatex = shutil.which("xelatex")
    if system_xelatex:
        _XELATEX_PATH = system_xelatex
        return _XELATEX_PATH

    raise FileNotFoundError(
        "xelatex not found. "
        "Install TeX Live, set XELATEX_PATH, or ensure the portable "
        "distribution is bundled correctly."
    )


def _get_texmf_root(xelatex_path: str) -> str | None:
    """从 xelatex 二进制位置推导 TEXMF 根目录。

    仅在 PyInstaller 打包后 + 检测到内嵌便携版 texmf.cnf 时返回路径。
    系统安装的 TeX Live 无需干预环境变量，返回 None。
    """
    if not getattr(sys, 'frozen', False):
        return None
    bin_dir = os.path.dirname(xelatex_path)          # .../bin/windows
    texlive_dir = os.path.dirname(os.path.dirname(bin_dir))  # .../texlive
    texmf_cnf = os.path.join(texlive_dir, "texmf.cnf")
    if os.path.isfile(texmf_cnf):
        return texlive_dir
    return None


def _copy_fmt_to_tmpdir(texmf_root: str, tmpdir: str) -> None:
    """复制 xelatex 格式文件到临时 TEXMFVAR 目录。

    TEXMFVAR 被设为临时目录（避免写入只读内嵌树），
    但 xelatex.fmt 需要位于 TEXMFVAR 可搜索路径中。
    """
    fmt_src = os.path.join(texmf_root, "texmf-var", "web2c", "xetex", "xelatex.fmt")
    if os.path.isfile(fmt_src):
        fmt_dst_dir = os.path.join(tmpdir, "web2c", "xetex")
        os.makedirs(fmt_dst_dir, exist_ok=True)
        fmt_dst = os.path.join(fmt_dst_dir, "xelatex.fmt")
        if not os.path.isfile(fmt_dst):
            shutil.copy2(fmt_src, fmt_dst)


def _copy_mapfiles_to_tmpdir(texmf_root: str, tmpdir: str) -> str:
    """复制字体映射/编码文件到临时目录（ASCII 路径）。

    xdvipdfmx 和 xetex 字体加载器可能无法处理 CJK 路径。
    将 fonts/map、fonts/enc、字体文件复制到临时目录。
    """
    texmf_dist = os.path.join(texmf_root, "texmf-dist")
    fonts_src = os.path.join(texmf_dist, "fonts")
    fonts_tmp = os.path.join(tmpdir, "fonts")

    # 映射和编码文件（小，必须复制）
    for sub in ["map", "enc", "cmap"]:
        src = os.path.join(fonts_src, sub)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(fonts_tmp, sub)
        if not os.path.isdir(dst):
            shutil.copytree(src, dst)

    # 字体文件本身（避免 CJK 路径干扰 fontspec / xdvipdfmx / FreeType2）
    for sub in ["opentype", "truetype", "type1", "tfm"]:
        src = os.path.join(fonts_src, sub)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(fonts_tmp, sub)
        if not os.path.isdir(dst):
            shutil.copytree(src, dst)

    return fonts_tmp


def _generate_runtime_fonts_conf(fonts_dir: str, tmpdir: str) -> str:
    """在运行时生成 fonts.conf，使用当前部署路径（而非构建时硬编码路径）。

    fonts_dir 应指向字体所在目录（如 tmpdir/fonts），避免 CJK 路径干扰 xdvipdfmx。

    返回 fonts.conf 文件路径。
    """
    fc_cache = os.path.join(tmpdir, "fonts", "cache")
    opentype = os.path.join(fonts_dir, "opentype")
    truetype = os.path.join(fonts_dir, "truetype")
    type1 = os.path.join(fonts_dir, "type1")

    os.makedirs(fc_cache, exist_ok=True)

    conf = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        '<fontconfig>\n'
        f'  <cachedir>{fc_cache.replace(os.sep, "/")}</cachedir>\n'
        f'  <dir>{opentype.replace(os.sep, "/")}</dir>\n'
        f'  <dir>{truetype.replace(os.sep, "/")}</dir>\n'
        f'  <dir>{type1.replace(os.sep, "/")}</dir>\n'
        '</fontconfig>\n'
    )

    conf_path = os.path.join(tmpdir, "fonts.conf")
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(conf)
    return conf_path


# ---- C1: _build_compile_env ----

def _build_compile_env(texmf_root: str | None, tmpdir: str,
                       fonts_tmp: str | None) -> dict | None:
    """组装 xelatex 编译环境变量 dict。

    texmf_root 为 None 时返回 None（系统 TeX 继承父进程 env）。
    texmf_root 不为 None 时返回 os.environ.copy() + 覆盖 ~15 个 env vars，
    字段名与值（含分号、路径拼接顺序）与现状逐字一致。
    """
    if texmf_root is None:
        return None

    env = os.environ.copy()
    texmf_dist = os.path.join(texmf_root, "texmf-dist")
    texmf_var = os.path.join(texmf_root, "texmf-var")

    env["TEXMFDIST"] = texmf_dist
    env["TEXMFVAR"] = tmpdir
    env["TEXMF"] = texmf_var + ";" + tmpdir + ";!!" + texmf_dist
    env["TEXMFCNF"] = texmf_root + ";" + texmf_dist + "/web2c"
    fc_dir = os.path.join(tmpdir, "fonts", "cache")
    os.makedirs(fc_dir, exist_ok=True)
    env["FC_CACHEDIR"] = fc_dir
    env["FONTCONFIG_PATH"] = tmpdir
    env["FONTCONFIG_FILE"] = os.path.join(tmpdir, "fonts.conf")

    env["TEXINPUTS"] = ".;" + texmf_dist + "/tex//"
    env["TEXINPUTS.latex"] = ".;" + texmf_dist + "/tex/{latex,generic,xetex,}//"
    env["TEXFORMATS"] = ".;" + tmpdir + "/web2c/{xetex,}//"

    if fonts_tmp:
        env["OPENTYPEFONTS"] = ".;" + fonts_tmp + "/opentype//"
        env["TTFONTS"] = ".;" + fonts_tmp + "/truetype//"
        env["T1FONTS"] = ".;" + fonts_tmp + "/type1//"
        env["TFMFONTS"] = ".;" + fonts_tmp + "/tfm//"
        env["TEXFONTMAPS"] = ".;" + fonts_tmp + "/map//"
        env["ENCFONTS"] = ".;" + fonts_tmp + "/enc//"
        env["TEXINPUTS"] = ".;" + texmf_dist + "/tex//;" + fonts_tmp + "/opentype//;" + fonts_tmp + "/truetype//"

    return env


# ---- C1: _diagnose_log ----

def _diagnose_log(log_path: str, tail_lines: int = 15,
                  include_error_colon: bool = False) -> tuple[str, str]:
    """从 xelatex 日志提取诊断信息。

    Args:
        tail_lines: 日志尾部行数（xelatex 阶段用 10，xdvipdfmx 阶段用 15）
        include_error_colon: 是否额外匹配小写 "error:" 前缀（仅 xdvipdfmx 阶段用）

    Returns:
        (diagnostic: str, tail: str) — 诊断行摘要与日志尾部。
    """
    log_text = ""
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8", errors="replace") as f:
            log_text = f.read()

    diag = []
    for ln in log_text.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue
        if (stripped.startswith("!") or
                "fatal" in stripped.lower() or
                "Error" in stripped):
            diag.append(stripped)
        elif include_error_colon and "error:" in stripped.lower():
            diag.append(stripped)

    tail = [ln.strip() for ln in log_text.splitlines()[-tail_lines:] if ln.strip()]
    return "\n".join(diag[-15:]), "\n".join(tail)


# ---- C1: _format_compile_error ----

def _format_compile_error(stage: str, retcode_info: str,
                          diagnostic: str, tail: str) -> str:
    """格式化编译错误 RuntimeError 消息文本。"""
    return (
        f"{stage} stage failed ({retcode_info}).\n"
        f"--- DIAGNOSTIC ---\n{diagnostic}\n"
        f"--- LOG TAIL ---\n{tail}"
    )


# ---- C1: _run_xelatex / _run_xdvipdfmx ----

def _run_with_timeout(cmd: list, compile_kwargs: dict, stage_name: str) -> int:
    """运行子进程，超时时终止子进程并抛 RuntimeError。

    subprocess.call/run 在 timeout 时抛 TimeoutExpired 但不终止子进程，
    改用 Popen + communicate(timeout=...)：超时自动 kill 并回收，避免
    xelatex/xdvipdfmx 残留进程持续占用 CPU 并写出半成品。
    """
    kw = dict(compile_kwargs)
    timeout = kw.pop('timeout', None)
    proc = subprocess.Popen(cmd, **kw)
    try:
        proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise RuntimeError(f"{stage_name} 编译超时（{timeout}秒），已终止进程")
    return proc.returncode


def _run_xelatex(xelatex_path: str, tmp_tex: str, tmpdir: str,
                 base: str, log_path: str,
                 build_env: dict | None) -> int:
    """运行 xelatex -no-pdf 生成 XDV。失败时抛出 RuntimeError。

    compile_kwargs 中的 subprocess 调用细节（subprocess.call、cwd、DEVNULL、
    Windows CREATE_NO_WINDOW / STARTUPINFO）严格保留原样。
    """
    cmd = [
        xelatex_path, "-no-pdf", "-interaction=nonstopmode",
        f'-output-directory={tmpdir}', tmp_tex,
    ]
    compile_kwargs = {
        'timeout': LATEX_COMPILE_TIMEOUT,
        'cwd': tmpdir,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
    }
    if build_env is not None:
        compile_kwargs['env'] = build_env
    if os.name == 'nt':
        compile_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        compile_kwargs['startupinfo'] = si

    retcode = _run_with_timeout(cmd, compile_kwargs, "XeLaTeX")
    # nonstopmode 下 xelatex 即使只有 minor warnings 也会返回非零，
    # 但 XDV 可能生成成功。以 XDV 是否有效为准。
    xdv_path = os.path.join(tmpdir, f"{base}.xdv")
    xdv_ok = os.path.isfile(xdv_path) and os.path.getsize(xdv_path) > 100
    if not xdv_ok:
        diagnostic, tail = _diagnose_log(log_path, tail_lines=10)
        raise RuntimeError(_format_compile_error(
            "XeLaTeX", f"retcode={retcode}", diagnostic, tail))
    return retcode


def _run_xdvipdfmx(xelatex_path: str, tmpdir: str, base: str,
                   xdv_path: str, log_path: str,
                   build_env: dict | None, texmf_root: str | None,
                   retcode1: int,
                   nt_startupinfo) -> str:
    """运行 xdvipdfmx 将 XDV 转为 PDF。失败时抛出 RuntimeError。

    返回生成的临时 PDF 路径。
    """
    _xdv_exe = "xdvipdfmx.exe" if os.name == 'nt' else "xdvipdfmx"
    xdvipdfmx_path = os.path.join(os.path.dirname(xelatex_path), _xdv_exe)
    if not os.path.isfile(xdvipdfmx_path) and os.name != 'nt':
        xdvipdfmx_path = os.path.join(os.path.dirname(xelatex_path), "xdvipdfmx.exe")
    tmp_pdf = os.path.join(tmpdir, f"{base}.pdf")
    cmd = [xdvipdfmx_path, "-o", tmp_pdf, xdv_path]
    compile_kwargs = {
        'timeout': LATEX_COMPILE_TIMEOUT,
        'cwd': tmpdir,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
    }
    if texmf_root and build_env is not None:
        env2 = build_env.copy()
        texmf_dist = os.path.join(texmf_root, "texmf-dist")
        env2["DVIPDFMXINPUTS"] = ".;" + texmf_dist + "/dvipdfmx//"
        compile_kwargs['env'] = env2
    if os.name == 'nt':
        compile_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        compile_kwargs['startupinfo'] = nt_startupinfo

    retcode2 = _run_with_timeout(cmd, compile_kwargs, "xdvipdfmx")

    # 检测 xdvipdfmx 阶段失败
    pdf_exists = os.path.isfile(tmp_pdf)
    pdf_size = os.path.getsize(tmp_pdf) if pdf_exists else 0
    is_stub_pdf = pdf_exists and pdf_size < 1024

    log_text = ""
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8", errors="replace") as f:
            log_text = f.read()
    has_fatal_error = (
        re.search(r'^Runaway argument\?', log_text, re.MULTILINE) is not None
        or re.search(r'^Emergency stop', log_text, re.MULTILINE) is not None
        or re.search(r'^No pages of output', log_text, re.MULTILINE) is not None
    )

    if retcode2 != 0 or is_stub_pdf or has_fatal_error:
        diagnostic, tail = _diagnose_log(log_path, tail_lines=15, include_error_colon=True)
        raise RuntimeError(_format_compile_error(
            "xdvipdfmx",
            f"xelatex_ret={retcode1}, xdvipdfmx_ret={retcode2}, "
            f"pdf_exists={pdf_exists}, pdf_size={pdf_size}",
            diagnostic, tail))

    return tmp_pdf


# ---- compile_to_pdf（编排主函数）----

def compile_to_pdf(tex_path: str, output_dir: str | None = None,
                   images_map: dict | None = None) -> str:
    """编译 .tex 文件为 PDF。

    在临时目录（ASCII 路径）编译以避免 xelatex 对中文路径的兼容问题，
    然后将 PDF 复制到目标 output_dir。

    Args:
        tex_path: .tex 文件路径
        output_dir: PDF 输出目录，默认为 .tex 同目录
        images_map: {section_title: {filename: source_path}} 图片映射，直接复制到临时目录

    Returns:
        生成的 PDF 文件路径

    Raises:
        FileNotFoundError: tex_path 不存在
        RuntimeError: xelatex 编译失败（含日志摘要）
    """
    if not os.path.isfile(tex_path):
        raise FileNotFoundError(f"TeX file not found: {tex_path}")

    if output_dir is None:
        output_dir = os.path.dirname(tex_path) or "."

    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(tex_path))[0]
    target_pdf = os.path.join(output_dir, f"{base}.pdf")

    # 创建临时目录用于编译（ASCII 路径，避免 xelatex 对中文路径的兼容问题）
    tmpdir = tempfile.mkdtemp(prefix="latex_compile_")
    try:
        tex_dir = os.path.dirname(tex_path) or "."
        tmp_tex = os.path.join(tmpdir, f"{base}.tex")

        # 定位 xelatex 并推导 texmf 根目录
        xelatex_path = _find_xelatex()
        texmf_root = _get_texmf_root(xelatex_path)

        # 内嵌便携版：将格式文件 + 字体映射复制到临时目录（ASCII 路径）
        # 避免 CJK 路径导致 xdvipdfmx 失败
        fonts_tmp = None
        runtime_fonts_conf = None
        if texmf_root:
            _copy_fmt_to_tmpdir(texmf_root, tmpdir)
            fonts_tmp = _copy_mapfiles_to_tmpdir(texmf_root, tmpdir)
            runtime_fonts_conf = _generate_runtime_fonts_conf(fonts_tmp, tmpdir)

        # 组装编译环境变量（texmf_root 为 None 时返回 None，主函数不传 env）
        build_env = _build_compile_env(texmf_root, tmpdir, fonts_tmp)

        # 复制 .tex 到临时目录
        shutil.copy2(tex_path, tmp_tex)

        # 从 images_map 直接复制图片到临时目录
        if images_map:
            for sec_title, imgs in images_map.items():
                sec_img_dir = os.path.join(tmpdir, sec_title, "images")
                os.makedirs(sec_img_dir, exist_ok=True)
                for fname, src in imgs.items():
                    shutil.copy2(src, os.path.join(sec_img_dir, fname))

        # 也复制 tex_dir 下的图片目录（兼容旧调用）
        for item in os.listdir(tex_dir):
            src = os.path.join(tex_dir, item)
            if os.path.isdir(src) and item not in (images_map or {}):
                dst = os.path.join(tmpdir, item)
                if not os.path.exists(dst):
                    shutil.copytree(src, dst)

        # 在临时目录中编译
        # 两步法：xelatex -no-pdf 生成 XDV，然后 xdvipdfmx 转 PDF。
        xdv_path = os.path.join(tmpdir, f"{base}.xdv")
        log_path = os.path.join(tmpdir, f"{base}.log")

        # 预计算 Windows STARTUPINFO（xdvipdfmx 复用）
        nt_startupinfo = None
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            nt_startupinfo = si

        retcode1 = _run_xelatex(xelatex_path, tmp_tex, tmpdir, base, log_path, build_env)
        tmp_pdf = _run_xdvipdfmx(xelatex_path, tmpdir, base, xdv_path, log_path,
                                 build_env, texmf_root, retcode1, nt_startupinfo)

        # 复制 PDF 到目标目录
        shutil.copy2(tmp_pdf, target_pdf)

    finally:
        # 清理临时目录
        shutil.rmtree(tmpdir, ignore_errors=True)

    return target_pdf
