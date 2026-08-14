#!/usr/bin/env python
"""小学数学 LaTeX→PDF 独立编译测试

模拟打包后的便携 TeX Live 环境，使用与 compile_to_pdf() 完全相同的
xelatex 调用逻辑，验证：
  1. 最小 tex 文件编译
  2. CJK 中文渲染（Fandol 字体）
  3. 数学公式渲染
  4. proofread_template.tex 完整模板编译
  5. paracol 双栏排版
  6. 字体缺失检测

用法:
    python -X utf8 tests/test_math_pdf.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED_TEXLIVE = os.path.join(PROJECT_ROOT, "bundled_texlive")
_BUNDLED_XELATEX = os.path.join(BUNDLED_TEXLIVE, "bin", "windows", "xelatex.exe")
_BUNDLED_XDVIPDFMX = os.path.join(BUNDLED_TEXLIVE, "bin", "windows", "xdvipdfmx.exe")

# 环境检查：bundled（模拟打包验证）或系统 xelatex（开发/CI）任一可用即运行编译测试
_USE_BUNDLED = os.path.isfile(_BUNDLED_XELATEX) and os.path.isfile(_BUNDLED_XDVIPDFMX)
_SYSTEM_XELATEX = shutil.which("xelatex")
_SYSTEM_XDVIPDFMX = shutil.which("xdvipdfmx")
_HAS_TEXLIVE = _USE_BUNDLED or (_SYSTEM_XELATEX and _SYSTEM_XDVIPDFMX)
_skip_no_texlive = unittest.skipUnless(
    _HAS_TEXLIVE,
    "需要 bundled_texlive（打包验证）或系统 xelatex（开发/CI）")

XELATEX = _BUNDLED_XELATEX if _USE_BUNDLED else _SYSTEM_XELATEX
XDVIPDFMX = _BUNDLED_XDVIPDFMX if _USE_BUNDLED else _SYSTEM_XDVIPDFMX

# ---- 辅助函数（精简自 pdf_compiler.py）----

def _get_texmf_root():
    """从内嵌 TeX Live 推导 TEXMF 根；系统模式返回 None（走系统配置）"""
    if not _USE_BUNDLED:
        return None
    texmf_cnf = os.path.join(BUNDLED_TEXLIVE, "texmf.cnf")
    if os.path.isfile(texmf_cnf):
        return BUNDLED_TEXLIVE
    return None


def _copy_fmt_to_tmpdir(tmpdir):
    """复制 xelatex.fmt 到临时目录（仅 bundled 模式需要）"""
    if not _USE_BUNDLED:
        return False
    texmf_root = BUNDLED_TEXLIVE
    fmt_src = os.path.join(texmf_root, "texmf-var", "web2c", "xetex", "xelatex.fmt")
    if os.path.isfile(fmt_src):
        fmt_dst_dir = os.path.join(tmpdir, "web2c", "xetex")
        os.makedirs(fmt_dst_dir, exist_ok=True)
        fmt_dst = os.path.join(fmt_dst_dir, "xelatex.fmt")
        if not os.path.isfile(fmt_dst):
            shutil.copy2(fmt_src, fmt_dst)
        return True
    return False


def _copy_mapfiles_to_tmpdir(tmpdir):
    """复制字体 map/字体文件（仅 bundled 模式需要）"""
    if not _USE_BUNDLED:
        return None
    texmf_root = BUNDLED_TEXLIVE
    texmf_dist = os.path.join(texmf_root, "texmf-dist")
    fonts_src = os.path.join(texmf_dist, "fonts")
    fonts_tmp = os.path.join(tmpdir, "fonts")
    if not os.path.isdir(fonts_src):
        return None
    for sub in ["map", "enc", "cmap", "opentype", "truetype", "type1", "tfm"]:
        src = os.path.join(fonts_src, sub)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(fonts_tmp, sub)
        if not os.path.isdir(dst):
            shutil.copytree(src, dst)
    return fonts_tmp


def _build_env(tmpdir, fonts_tmp=None):
    """构造 xelatex 环境变量。

    bundled 模式：完整 TEXMF/FONTCONFIG 定制（模拟打包环境）；
    系统模式：直接用系统配置（系统 TeX Live 自带字体与 kpathsea 配置）。
    """
    if not _USE_BUNDLED:
        return os.environ.copy()

    texmf_root = BUNDLED_TEXLIVE
    texmf_dist = os.path.join(texmf_root, "texmf-dist")
    texmf_var = os.path.join(texmf_root, "texmf-var")

    env = os.environ.copy()
    env["TEXMFDIST"] = texmf_dist
    env["TEXMFVAR"] = tmpdir
    env["TEXMF"] = texmf_var + ";" + tmpdir + ";!!" + texmf_dist
    env["TEXMFCNF"] = texmf_root + ";" + texmf_dist + "/web2c"

    fc_dir = os.path.join(tmpdir, "fonts", "cache")
    os.makedirs(fc_dir, exist_ok=True)
    env["FC_CACHEDIR"] = fc_dir
    env["FONTCONFIG_PATH"] = tmpdir

    # 生成运行时 fonts.conf
    fc_conf = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        '<fontconfig>\n'
        f'  <cachedir>{fc_dir.replace(os.sep, "/")}</cachedir>\n'
        f'  <dir>{os.path.join(fonts_tmp or "", "opentype").replace(os.sep, "/")}</dir>\n'
        f'  <dir>{os.path.join(fonts_tmp or "", "truetype").replace(os.sep, "/")}</dir>\n'
        f'  <dir>{os.path.join(fonts_tmp or "", "type1").replace(os.sep, "/")}</dir>\n'
        '</fontconfig>\n'
    )
    conf_path = os.path.join(tmpdir, "fonts.conf")
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(fc_conf)
    env["FONTCONFIG_FILE"] = conf_path

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


def _compile_tex(tex_source, tex_name="test"):
    """完整编译流程：tex → xdv → pdf，返回 (pdf_path, log_text)"""
    tmpdir = tempfile.mkdtemp(prefix="math_pdf_test_")
    try:
        # 复制运行时文件
        _copy_fmt_to_tmpdir(tmpdir)
        fonts_tmp = _copy_mapfiles_to_tmpdir(tmpdir)
        env = _build_env(tmpdir, fonts_tmp)

        # 写入 .tex
        tex_path = os.path.join(tmpdir, f"{tex_name}.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_source)

        xdv_path = os.path.join(tmpdir, f"{tex_name}.xdv")
        log_path = os.path.join(tmpdir, f"{tex_name}.log")
        pdf_path = os.path.join(tmpdir, f"{tex_name}.pdf")

        compile_kwargs = {
            'timeout': 120,
            'cwd': tmpdir,
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
            'env': env,
        }
        if os.name == 'nt':
            compile_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        # Step 1: xelatex -no-pdf
        cmd1 = [XELATEX, "-no-pdf", "-interaction=nonstopmode",
                f"-output-directory={tmpdir}", tex_path]
        ret1 = subprocess.call(cmd1, **compile_kwargs)
        xdv_ok = os.path.isfile(xdv_path) and os.path.getsize(xdv_path) > 100

        log_text = ""
        if os.path.isfile(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as f:
                log_text = f.read()

        if not xdv_ok:
            return None, log_text, ret1

        # Step 2: xdvipdfmx
        cmd2 = [XDVIPDFMX, "-o", pdf_path, xdv_path]
        compile_kwargs2 = {
            'timeout': 120,
            'cwd': tmpdir,
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
            'env': env,
        }
        env2 = env.copy()
        if _USE_BUNDLED:
            texmf_dist = os.path.join(BUNDLED_TEXLIVE, "texmf-dist")
            env2["DVIPDFMXINPUTS"] = ".;" + texmf_dist + "/dvipdfmx//"
        compile_kwargs2['env'] = env2
        if os.name == 'nt':
            compile_kwargs2['creationflags'] = subprocess.CREATE_NO_WINDOW

        ret2 = subprocess.call(cmd2, **compile_kwargs2)
        if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 1024:
            # 复制 PDF 出来（tmpdir 会被清理）
            result_pdf = os.path.join(tempfile.gettempdir(), f"{tex_name}_test.pdf")
            shutil.copy2(pdf_path, result_pdf)
            return result_pdf, log_text, (ret1, ret2)
        return None, log_text, (ret1, ret2)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════

@_skip_no_texlive
class TestMinimalLatex(unittest.TestCase):
    """最小化 LaTeX 编译测试"""

    def test_minimal_english(self):
        """纯英文最小文档"""
        tex = r"""
\documentclass{article}
\begin{document}
Hello World
\end{document}
"""
        pdf, log, ret = _compile_tex(tex, "minimal_en")
        self.assertIsNotNone(pdf, f"编译失败！\nLOG TAIL:\n{_log_tail(log)}")
        self.assertTrue(os.path.isfile(pdf))
        self.assertGreater(os.path.getsize(pdf), 1000)
        print(f"  ✅ PDF: {pdf} ({os.path.getsize(pdf)} bytes)")

    def test_minimal_cjk(self):
        """CJK 中文渲染（Fandol 字体）"""
        tex = r"""
\documentclass[12pt,a4paper]{article}
\usepackage{xeCJK}
\setCJKmainfont{FandolSong-Regular.otf}[
  BoldFont=FandolSong-Bold.otf,
  ItalicFont=FandolKai-Regular.otf]
\setCJKsansfont{FandolHei-Regular.otf}[
  BoldFont=FandolHei-Bold.otf]
\setCJKmonofont{FandolKai-Regular.otf}
\begin{document}
小学数学校对测试：一二三四五六七八九十。

\textbf{粗体中文} \textit{斜体中文}

数学符号：$1 + 2 = 3$，$x^2 + y^2 = z^2$

分数：$\frac{1}{2} + \frac{2}{3} = \frac{7}{6}$
\end{document}
"""
        pdf, log, ret = _compile_tex(tex, "minimal_cjk")
        self.assertIsNotNone(pdf, f"编译失败！\nLOG TAIL:\n{_log_tail(log)}")
        self.assertGreater(os.path.getsize(pdf), 1000)
        # 检查无致命错误
        self.assertNotIn("Emergency stop", log, "存在 Emergency stop 错误")
        print(f"  ✅ PDF: {pdf} ({os.path.getsize(pdf)} bytes)")

    def test_math_formulas(self):
        """小学数学常用公式"""
        tex = r"""
\documentclass[12pt,a4paper]{article}
\usepackage{xeCJK}
\usepackage{amsmath,amssymb}
\setCJKmainfont{FandolSong-Regular.otf}[
  BoldFont=FandolSong-Bold.otf,
  ItalicFont=FandolKai-Regular.otf]
\setCJKsansfont{FandolHei-Regular.otf}[
  BoldFont=FandolHei-Bold.otf]
\setmainfont{texgyretermes-regular.otf}
\begin{document}
\section*{小学数学公式测试}

四则运算：$12 + 34 = 46$，$100 - 37 = 63$，$25 \times 4 = 100$，$99 \div 3 = 33$

分数：$\frac{3}{4} + \frac{1}{8} = \frac{7}{8}$

小数：$0.25 + 0.75 = 1.00$

百分数：$25\% = 0.25 = \frac{1}{4}$

几何：$S_{\text{长方形}} = a \times b$，$C_{\text{圆}} = 2\pi r$

方程：$2x + 3 = 11$，解得 $x = 4$

单位换算：$1\text{m} = 100\text{cm}$，$1\text{kg} = 1000\text{g}$
\end{document}
"""
        pdf, log, ret = _compile_tex(tex, "math_formulas")
        self.assertIsNotNone(pdf, f"编译失败！\nLOG TAIL:\n{_log_tail(log)}")
        self.assertNotIn("Emergency stop", log)
        print(f"  ✅ PDF: {pdf} ({os.path.getsize(pdf)} bytes)")


@_skip_no_texlive
class TestProofreadTemplate(unittest.TestCase):
    """验证校对模板关键组件可编译"""

    def test_template_structure(self):
        """模板基础结构（不含 paracol 内容）"""
        template_path = os.path.join(
            PROJECT_ROOT, "shared", "templates", "proofread_template.tex")
        with open(template_path, encoding="utf-8") as f:
            template = f.read()

        # 替换 {{CONTENT}} 为简单内容
        tex = template.replace("{{CONTENT}}", r"""
\section*{测试题目}
这是一道小学计算题：计算 $25 \times 4 \div 2$ 的结果。

答案：$50$。
""")
        pdf, log, ret = _compile_tex(tex, "template_basic")
        self.assertIsNotNone(pdf, f"编译失败！\nLOG TAIL:\n{_log_tail(log)}")
        print(f"  ✅ PDF: {pdf} ({os.path.getsize(pdf)} bytes)")

    def test_paracol_dual_column(self):
        """paracol 双栏排版"""
        template_path = os.path.join(
            PROJECT_ROOT, "shared", "templates", "proofread_template.tex")
        with open(template_path, encoding="utf-8") as f:
            template = f.read()

        content = r"""
\begin{paracol}{2}

\section*{第1题：口算}

\textbf{题目：}计算 $36 + 64 =$ \_\_\_\_\_

\textbf{答案：}$100$

\switchcolumn

\textbf{\Large 🔴 修改意见}

\correctionbox{\redcircled{1} 改为：$36 + 64 = 100$ \\ 修改原因：原答案写成了 $99$，正确结果是 $100$。}

\switchcolumn*

\end{paracol}

\newpage

\begin{paracol}{2}

\section*{第2题：应用题}

\textbf{题目：}小明买了 3 支铅笔，每支 2 元，他一共花了多少钱？

\textbf{答案：}6 元。

\switchcolumn

\textbf{\Large 🔴 修改意见}

\correctionbox{\redcircled{1} 改为：6 元 \\ 修改原因：答案正确，解析中把 $3 \times 2$ 写成了 $3 + 2$。}

\switchcolumn*

\end{paracol}
"""
        tex = template.replace("{{CONTENT}}", content)
        pdf, log, ret = _compile_tex(tex, "paracol_dual")
        self.assertIsNotNone(pdf, f"编译失败！\nLOG TAIL:\n{_log_tail(log)}")
        print(f"  ✅ PDF: {pdf} ({os.path.getsize(pdf)} bytes)")

    def test_corrmark_math(self):
        r"""\corrmark 内嵌数学公式"""
        template_path = os.path.join(
            PROJECT_ROOT, "shared", "templates", "proofread_template.tex")
        with open(template_path, encoding="utf-8") as f:
            template = f.read()

        content = r"""
\begin{paracol}{2}

计算：$\frac{1}{2} + \frac{1}{3} = \frac{5}{6}$

原解析中 \corrmark{$\frac{2}{3}$}{1} 应改为 $\frac{5}{6}$。

\switchcolumn

\correctionbox{\redcircled{1} 改为：$\frac{5}{6}$ \\ 修改原因：$\frac{1}{2} + \frac{1}{3} = \frac{3}{6} + \frac{2}{6} = \frac{5}{6}$，不是 $\frac{2}{3}$。}

\switchcolumn*

\end{paracol}
"""
        tex = template.replace("{{CONTENT}}", content)
        pdf, log, ret = _compile_tex(tex, "corrmark_math")
        self.assertIsNotNone(pdf, f"编译失败！\nLOG TAIL:\n{_log_tail(log)}")
        print(f"  ✅ PDF: {pdf} ({os.path.getsize(pdf)} bytes)")

    def test_ulem_formatting(self):
        """下划线/删除线/着重号"""
        template_path = os.path.join(
            PROJECT_ROOT, "shared", "templates", "proofread_template.tex")
        with open(template_path, encoding="utf-8") as f:
            template = f.read()

        content = r"""
\begin{paracol}{2}

\textbf{题目原文：}小明有 \uline{12} 个苹果，吃了 \sout{3} 个，还剩 \uwave{9} 个。

\switchcolumn

\correctionbox{\redcircled{1} 改为：\uline{12} → 12 颗 \\ 修改原因：苹果应该用"颗"不是"个"。}

\switchcolumn*

\end{paracol}
"""
        tex = template.replace("{{CONTENT}}", content)
        pdf, log, ret = _compile_tex(tex, "ulem_format")
        self.assertIsNotNone(pdf, f"编译失败！\nLOG TAIL:\n{_log_tail(log)}")
        print(f"  ✅ PDF: {pdf} ({os.path.getsize(pdf)} bytes)")


@_skip_no_texlive
class TestPdfCompilerIntegration(unittest.TestCase):
    """通过 pdf_compiler.compile_to_pdf 直接编译"""

    def test_compile_minimal_tex(self):
        """用 compile_to_pdf 编译最小 tex 文件"""
        from shared.pdf_compiler import compile_to_pdf

        tex_content = r"""
\documentclass[12pt,a4paper]{article}
\usepackage{xeCJK}
\setCJKmainfont{FandolSong-Regular.otf}[
  BoldFont=FandolSong-Bold.otf,
  ItalicFont=FandolKai-Regular.otf]
\setCJKsansfont{FandolHei-Regular.otf}[
  BoldFont=FandolHei-Bold.otf]
\setmainfont{texgyretermes-regular.otf}
\usepackage{amsmath}
\usepackage{paracol}
\usepackage{xcolor}
\usepackage[normalem]{ulem}
\usepackage{tikz}
\begin{document}
小学数学 PDF 编译测试。

$1 + 1 = 2$

$\frac{3}{4} \times 8 = 6$
\end{document}
"""
        tmpdir = tempfile.mkdtemp(prefix="math_pdf_integration_")
        try:
            tex_path = os.path.join(tmpdir, "test.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex_content)

            pdf_path = compile_to_pdf(tex_path, output_dir=tmpdir)
            self.assertTrue(os.path.isfile(pdf_path))
            self.assertGreater(os.path.getsize(pdf_path), 1000)
            print(f"  ✅ PDF: {pdf_path} ({os.path.getsize(pdf_path)} bytes)")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestPdfCompilerCleanup(unittest.TestCase):
    """回归：compile_to_pdf 在 xelatex 定位失败等预编译异常时必须清理临时目录。"""

    def test_xelatex_missing_still_cleans_tmpdir(self):
        from unittest import mock

        from shared import pdf_compiler

        tmpdir = tempfile.mkdtemp(prefix="cleanup_probe_")
        tex_path = os.path.join(tmpdir, "test.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write("\\documentclass{article}\n\\begin{document}x\\end{document}\n")

        with mock.patch.object(pdf_compiler, "_find_xelatex",
                               side_effect=FileNotFoundError("xelatex 不存在")), \
                mock.patch.object(pdf_compiler, "tempfile") as mock_tf:
            mock_tf.mkdtemp.return_value = "/tmp/latex_compile_fake_test"
            with mock.patch.object(pdf_compiler.shutil, "rmtree") as mock_rm:
                with self.assertRaises(FileNotFoundError):
                    pdf_compiler.compile_to_pdf(tex_path, output_dir=tmpdir)
                # 临时目录必须被清理（rmtree 被调用）
                mock_rm.assert_called_once_with("/tmp/latex_compile_fake_test",
                                                ignore_errors=True)
        shutil.rmtree(tmpdir, ignore_errors=True)


def _log_tail(log_text, n=20):
    """提取日志尾部和错误行"""
    if not log_text:
        return "(无日志)"
    lines = log_text.splitlines()
    errors = [l.strip() for l in lines if l.strip().startswith("!") or "Error" in l or "fatal" in l.lower()]
    tail = [l.strip() for l in lines[-n:] if l.strip()]
    parts = []
    if errors:
        parts.append("--- ERRORS ---")
        parts.extend(errors[-10:])
    parts.append("--- TAIL ---")
    parts.extend(tail)
    return "\n".join(parts)


def check_environment():
    """编译前环境检查"""
    print("\n" + "=" * 60)
    print("  环境检查")
    print("=" * 60)

    if _USE_BUNDLED:
        checks = {
            "xelatex.exe (bundled)": os.path.isfile(XELATEX),
            "xdvipdfmx.exe (bundled)": os.path.isfile(XDVIPDFMX),
            "texmf.cnf": os.path.isfile(os.path.join(BUNDLED_TEXLIVE, "texmf.cnf")),
            "xelatex.fmt": os.path.isfile(os.path.join(
                BUNDLED_TEXLIVE, "texmf-var", "web2c", "xetex", "xelatex.fmt")),
            "FandolSong": os.path.isfile(os.path.join(
                BUNDLED_TEXLIVE, "texmf-dist", "fonts", "opentype", "public",
                "fandol", "FandolSong-Regular.otf")),
            "FandolHei": os.path.isfile(os.path.join(
                BUNDLED_TEXLIVE, "texmf-dist", "fonts", "opentype", "public",
                "fandol", "FandolHei-Regular.otf")),
            "texgyretermes": os.path.isfile(os.path.join(
                BUNDLED_TEXLIVE, "texmf-dist", "fonts", "opentype", "public",
                "tex-gyre", "texgyretermes-regular.otf")),
            "DejaVuSans": os.path.isfile(os.path.join(
                BUNDLED_TEXLIVE, "texmf-dist", "fonts", "truetype", "public",
                "dejavu", "DejaVuSans.ttf")),
        }
    else:
        # 系统模式：走系统 TeX Live 的字体与格式
        def _kpse(name):
            try:
                out = subprocess.run(
                    ["kpsewhich", name], capture_output=True, text=True, timeout=10)
                return bool(out.stdout.strip())
            except Exception:
                return False

        checks = {
            "xelatex (system)": bool(_SYSTEM_XELATEX),
            "xdvipdfmx (system)": bool(_SYSTEM_XDVIPDFMX),
            "FandolSong": _kpse("FandolSong-Regular.otf"),
            "FandolHei": _kpse("FandolHei-Regular.otf"),
            "texgyretermes": _kpse("texgyretermes-regular.otf"),
        }

    checks["proofread_template.tex"] = os.path.isfile(os.path.join(
        PROJECT_ROOT, "shared", "templates", "proofread_template.tex"))

    all_ok = True
    for name, ok in checks.items():
        status = "✅" if ok else "❌"
        if not ok:
            all_ok = False
        print(f"  {status} {name}")

    if not all_ok:
        print("\n⚠️  部分文件缺失，编译测试可能失败！")
    else:
        print("\n✅ 所有依赖完整")

    return all_ok


if __name__ == "__main__":
    check_environment()
    print("\n" + "=" * 60)
    print("  LaTeX→PDF 编译测试")
    print("=" * 60)
    unittest.main(verbosity=2)
