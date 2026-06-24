"""
测试打包后的便携版 TeX Live 是否能正常生成 PDF
"""
import io
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def test_xelatex_exists():
    """检查 xelatex.exe 是否存在于打包目录"""
    xelatex_path = r"dist\高中物理\_internal\texlive\bin\windows\xelatex.exe"
    assert os.path.isfile(xelatex_path), f"xelatex not found: {xelatex_path}"
    print("  OK: xelatex exists: %s" % xelatex_path)
    return xelatex_path


def test_texmf_structure(xelatex_path):
    """检查 texmf 目录结构是否完整"""
    bin_dir = os.path.dirname(xelatex_path)
    texlive_dir = os.path.dirname(os.path.dirname(bin_dir))
    
    checks = [
        ("texmf.cnf", os.path.join(texlive_dir, "texmf.cnf")),
        ("texmf-dist", os.path.join(texlive_dir, "texmf-dist")),
        ("texmf-var", os.path.join(texlive_dir, "texmf-var")),
        ("xelatex.fmt", os.path.join(texlive_dir, "texmf-var", "web2c", "xetex", "xelatex.fmt")),
        ("ctex.sty", os.path.join(texlive_dir, "texmf-dist", "tex", "latex", "ctex", "ctex.sty")),
        ("fontspec.sty", os.path.join(texlive_dir, "texmf-dist", "tex", "latex", "fontspec", "fontspec.sty")),
    ]
    
    all_ok = True
    for name, path in checks:
        exists = os.path.exists(path)
        if exists:
            print("  OK: %s exists" % name)
        else:
            print("  FAIL: %s missing: %s" % (name, path))
            all_ok = False
    return texlive_dir, all_ok


def compile_test_tex(xelatex_path, texlive_dir):
    """使用打包后的 xelatex 编译测试 LaTeX 文件"""
    tmpdir = tempfile.mkdtemp(prefix="test_tex_")
    tex_path = os.path.join(tmpdir, "test.tex")
    
    tex_content = r"""
\documentclass{ctexart}
\usepackage{amsmath}
\begin{document}
\section{测试文档}

这是一个中文测试文档。

数学公式：$E=mc^2$

\begin{equation}
\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
\end{equation}

物理公式：$F=ma$

\end{document}
"""
    
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex_content)
    
    try:
        texmf_dist = os.path.join(texlive_dir, "texmf-dist")
        texmf_var = os.path.join(texlive_dir, "texmf-var")
        
        env = os.environ.copy()
        env["TEXMFDIST"] = texmf_dist
        env["TEXMFVAR"] = tmpdir
        env["TEXMF"] = texmf_var + ";" + tmpdir + ";!!" + texmf_dist
        env["TEXMFCNF"] = texlive_dir + ";" + texmf_dist + "/web2c"
        
        fonts_tmp = os.path.join(tmpdir, "fonts")
        fonts_src = os.path.join(texmf_dist, "fonts")
        
        for sub in ["map", "enc", "cmap"]:
            src = os.path.join(fonts_src, sub)
            if os.path.isdir(src):
                dst = os.path.join(fonts_tmp, sub)
                shutil.copytree(src, dst)
        
        for sub in ["opentype", "truetype", "type1", "tfm"]:
            src = os.path.join(fonts_src, sub)
            if os.path.isdir(src):
                dst = os.path.join(fonts_tmp, sub)
                shutil.copytree(src, dst)
        
        fc_cache = os.path.join(tmpdir, "fonts", "cache")
        os.makedirs(fc_cache, exist_ok=True)
        
        opentype = os.path.join(fonts_tmp, "opentype")
        truetype = os.path.join(fonts_tmp, "truetype")
        type1 = os.path.join(fonts_tmp, "type1")
        
        conf = (
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
            '<fontconfig>\n'
            '  <cachedir>%s</cachedir>\n'
            '  <dir>%s</dir>\n'
            '  <dir>%s</dir>\n'
            '  <dir>%s</dir>\n'
            '</fontconfig>\n'
        ) % (fc_cache.replace(os.sep, "/"), opentype.replace(os.sep, "/"),
             truetype.replace(os.sep, "/"), type1.replace(os.sep, "/"))
        
        conf_path = os.path.join(tmpdir, "fonts.conf")
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(conf)
        
        env["FC_CACHEDIR"] = fc_cache
        env["FONTCONFIG_PATH"] = tmpdir
        env["FONTCONFIG_FILE"] = conf_path
        
        env["TEXINPUTS"] = ".;" + texmf_dist + "/tex//"
        env["TEXFORMATS"] = ".;" + texmf_var + "/web2c/{xetex,}//;" + tmpdir + "/web2c/{xetex,}//"
        
        env["OPENTYPEFONTS"] = ".;" + fonts_tmp + "/opentype//"
        env["TTFONTS"] = ".;" + fonts_tmp + "/truetype//"
        env["T1FONTS"] = ".;" + fonts_tmp + "/type1//"
        env["TFMFONTS"] = ".;" + fonts_tmp + "/tfm//"
        env["TEXFONTMAPS"] = ".;" + fonts_tmp + "/map//"
        env["ENCFONTS"] = ".;" + fonts_tmp + "/enc//"
        
        fmt_src = os.path.join(texmf_var, "web2c", "xetex", "xelatex.fmt")
        if os.path.isfile(fmt_src):
            fmt_dst_dir = os.path.join(tmpdir, "web2c", "xetex")
            os.makedirs(fmt_dst_dir, exist_ok=True)
            fmt_dst = os.path.join(fmt_dst_dir, "xelatex.fmt")
            shutil.copy2(fmt_src, fmt_dst)
        
        xdv_path = os.path.join(tmpdir, "test.xdv")
        log_path = os.path.join(tmpdir, "test.log")
        
        print("  Executing: xelatex -no-pdf...")
        cmd1 = [
            xelatex_path, "-no-pdf", "-interaction=nonstopmode",
            "-output-directory=%s" % tmpdir, tex_path,
        ]
        
        kwargs = {
            'timeout': 120,
            'cwd': tmpdir,
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
            'env': env,
        }
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = si
        
        retcode1 = subprocess.call(cmd1, **kwargs)
        xdv_ok = os.path.isfile(xdv_path) and os.path.getsize(xdv_path) > 100
        
        if not xdv_ok:
            if os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    log_text = f.read()
                print("\n--- xelatex log ---")
                print(log_text[-3000:])
            raise RuntimeError("xelatex stage failed (retcode=%d)" % retcode1)
        
        print("  OK: xelatex stage succeeded")
        
        print("  Executing: xdvipdfmx...")
        xdvipdfmx_path = os.path.join(os.path.dirname(xelatex_path), "xdvipdfmx.exe")
        tmp_pdf = os.path.join(tmpdir, "test.pdf")
        cmd2 = [xdvipdfmx_path, "-o", tmp_pdf, xdv_path]
        
        kwargs2 = kwargs.copy()
        env2 = env.copy()
        env2["DVIPDFMXINPUTS"] = ".;" + texmf_dist + "/dvipdfmx//"
        kwargs2['env'] = env2
        
        retcode2 = subprocess.call(cmd2, **kwargs2)
        
        if retcode2 != 0 or not os.path.isfile(tmp_pdf) or os.path.getsize(tmp_pdf) < 1024:
            if os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    log_text = f.read()
                print("\n--- xdvipdfmx log ---")
                print(log_text[-3000:])
            raise RuntimeError("xdvipdfmx stage failed (retcode=%d)" % retcode2)
        
        print("  OK: xdvipdfmx stage succeeded")
        
        pdf_size = os.path.getsize(tmp_pdf)
        print("  OK: PDF generated, size: %.1f KB" % (pdf_size / 1024.0))
        
        output_dir = "test_output"
        os.makedirs(output_dir, exist_ok=True)
        final_pdf = os.path.join(output_dir, "test_output.pdf")
        shutil.copy2(tmp_pdf, final_pdf)
        print("  OK: PDF saved to: %s" % final_pdf)
        
        return final_pdf
        
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 60)
    print("Testing bundled TeX Live")
    print("=" * 60)
    
    try:
        print("\n1. Checking xelatex...")
        xelatex_path = test_xelatex_exists()
        
        print("\n2. Checking texmf structure...")
        texlive_dir, struct_ok = test_texmf_structure(xelatex_path)
        
        print("\n3. Compiling test LaTeX...")
        compile_test_tex(xelatex_path, texlive_dir)
        
        print("\n" + "=" * 60)
        print("All tests PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print("\nTEST FAILED: %s" % str(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)
