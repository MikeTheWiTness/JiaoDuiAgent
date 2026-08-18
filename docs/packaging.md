# 打包指南

## 环境要求

- Windows 10+
- Python 3.12
- TeX Live 2026（仅构建时需要，用于提取最小 TeX 发行版）
- PyInstaller 6.x

## 两步构建

### 1. 提取便携 TeX 发行版

从本机 TeX Live 中提取编译 PDF 所需的最小文件集：

```bash
python tools/build_minimal_texlive.py
```

生成 `bundled_texlive/` 目录（约 80 MB），包含：

```
bundled_texlive/
  texmf.cnf          # kpathsea 路径配置
  fonts.conf         # fontconfig 字体目录配置
  bin/windows/       # xelatex.exe + xdvipdfmx.exe + 依赖 DLL（xetex.dll, icudt78.dll 等）
  texmf-dist/        # 最小 LaTeX 包集（~300 个文件）
    dvipdfmx/        # dvipdfmx.cfg（xdvipdfmx 字体映射配置）
    tex/latex/       # ctex, amsmath, tikz, mhchem, fontspec 等
    fonts/           # Fandol（CJK）、TeX Gyre Termes（拉丁）、DejaVu Sans（符号）
      misc/xetex/fontmapping/base/  # tex-text.tec（xetex 连字映射）
    web2c/texmf.cnf  # 引擎内存参数（hyph_size, trie_size 等）
  texmf-var/
    web2c/xetex/xelatex.fmt  # 预编译格式文件
```

**原理**：`build_minimal_texlive.py` 会生成两份测试 `.tex` 文档（一份含 ctex + 全部宏包，一份含基础 article），用 `xelatex -recorder` 编译，`.fls` 文件记录了编译过程中读取的每一个文件。脚本解析 `.fls`，只复制被引用到的文件。字体文件（.otf/.ttf/.pfb）、字体映射（tex-text.tec）和 xdvipdfmx 配置（dvipdfmx.cfg）不由 kpathsea 追踪，需通过 `copy_fonts()`、`copy_font_mapping()` 和 `copy_dvipdfmx_config()` 显式复制。

每次 TeX Live 升级或模板宏包变更后，需重新运行此脚本重建 `bundled_texlive/`。

### 2. 打包 EXE

打包指定学科（以高中物理为例）：

```bash
pyinstaller specs/高中物理.spec
```

输出在 `dist/高中物理/`。

如需打包多个学科，为每个学科单独准备 `.spec` 文件，分别执行。

## 输出结构

```
dist/高中物理/
  高中物理.exe              # 主程序（GUI）
  config.json              # 学科配置（exe 同级，方便手动编辑）
  _internal/
    core/                  # 通用工具层
    shared/                # 共享工具库（sympy_tools, web_tools, latex_generator, pdf_compiler）
    ui/                    # UI 组件库 + 默认模板
    templates/             # LaTeX 模板 proofread_template.tex
    texlive/               # 便携 TeX 发行版
    ...                    # Python 依赖（sympy, tkinter, PIL 等）
```

总大小约 200 MB，其中 TeX 占 80 MB，Python 依赖占其余部分。

**注意**：`config.json` 放在 exe 同级而非 `_internal` 内，方便用户手动编辑学科配置。`.env` 也在 exe 同级，运行时自动生成。

## Spec 文件说明

每个学科对应一个 `.spec` 文件，放在 `specs/` 目录下。以小学数学为例：

```python
# specs/小学数学.spec
# -*- mode: python ; coding: utf-8 -*-
import os
import sys

spec_file = os.path.abspath(SPECPATH)
project_root = os.path.dirname(spec_file)
sys.path.insert(0, project_root)

subject_dir = os.path.join(project_root, 'subjects', '小学数学v3.0')

a = Analysis(
    [os.path.join(subject_dir, 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        # 注意：config.json 放在 '.'，即 _internal 根目录
        # 首次运行时由 main.py 自动复制到 exe 同级（方便用户编辑）
        (os.path.join(subject_dir, 'config.json'), '.'),
        (os.path.join(subject_dir, 'subject.py'), '.'),    # 学科模块
        (os.path.join(subject_dir, 'app.py'), '.'),         # 应用模块
        (os.path.join(project_root, 'shared/templates'), 'templates'),
        (os.path.join(project_root, 'bundled_texlive'), 'texlive'),
    ],
	    hiddenimports=[
	        'core',
	        'core.parsing',
	        'core.api_client',
	        'core.pandoc_utils',
	        'core.env_config',
	        'core.logging_utils',
	        'core.config_loader',
	        'core.defaults',
	        'core.manual_split',
	        'core.session_context',
	        'core.format_enforcement',
	        'core.idml_extractor',
	        'shared',
	        'shared.sympy_tools',
	        'shared.sympy_tools.tools',
	        'shared.sympy_tools.templates',
	        'shared.sympy_tools.sandbox',
	        'shared.sympy_tools.safety',
	        'shared.web_tools',
	        'shared.latex_generator',
	        'shared.pdf_compiler',
	        'shared.free_proofread',
	        'shared.smart_split',
	        'shared.review_mode',
	        'shared.docx_comments',
	        'shared.docx_format_enhancer',
	        'shared.chinese_classics_tools',
	        'shared.bash_tool',
	        'shared.split_post_utils',
	        'shared.text_nav_tools',
	        'shared.decor_utils',
	        'shared.image_utils',
	        'ui',
	        'ui.widgets',
	        'ui.pipeline',
	        'ui.default_app',
	        'sympy',
	        'sympy.parsing',
	        'sympy.parsing.sympy_parser',
	        'PIL',
	        'PIL.Image',
	        'docx',
	        'lxml',
	        'requests',
	        'pydantic',
	        'langchain_core',
	        'langchain_core.tools',
	        'langchain_core.messages',
	        'langchain_core.output_parsers',
	    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'pytest', 'matplotlib', 'scipy', 'numpy'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='小学数学',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='小学数学',
)
```

### 关键配置要点

1. **动态路径解析**：spec 文件中使用 `SPECPATH`（PyInstaller 内置变量）获取 spec 文件所在目录，从而定位项目根目录。不要使用 `sys.argv[0]`，因为其路径可能不准确。

2. **学科目录统一放在 `subjects/` 下**：所有学科放在 `subjects/` 目录下，命名格式为 `{学段}{学科}v{版本号}`（如 `小学数学v3.0`）。

3. **必需的 datas 配置**：除了 `config.json`，还必须包含 `subject.py` 和 `app.py`，因为 `main.py` 通过 `importlib.util` 动态加载这两个模块。

4. **config.json 放置策略**：
   - `config.json` 在 datas 中打包到 `_internal/` 根目录（作为内置默认配置）
   - 首次运行时，`main.py` 自动将其复制到 exe 同级目录
   - 用户可编辑 exe 同级的 `config.json`，程序优先读取此文件
   - 这样既保证开箱即用，又方便用户自定义

5. **打包后路径处理**：`main.py` 中需使用 `sys._MEIPASS` 来定位打包后的资源文件：

```python
def _get_resource_path(relative_path):
    """获取内置资源路径（_internal 内）。"""
    try:
        base_path = sys._MEIPASS  # PyInstaller 临时目录
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def _get_subject_dir():
    """获取学科目录（存放 config.json 和 .env 的目录）。
    - 打包后：exe 同级目录
    - 开发时：学科模块所在目录
    """
    try:
        exe_dir = os.path.dirname(sys.executable)
        return exe_dir
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))
```

6. **hiddenimports**：必须列出 `core/`、`shared/`、`ui/` 的所有子模块，因为它们是动态导入的，PyInstaller 无法自动检测。如果新增了模块（如 `free_proofread`、`smart_split`、`review_mode` 等），记得同步更新。

7. **排除不必要的大依赖**：使用 `excludes` 排除 `matplotlib`、`scipy`、`numpy` 等不使用的大库，可显著减小体积。

## 运行时 xelatex 发现机制

`shared/pdf_compiler.py` 按以下优先级查找 xelatex：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `XELATEX_PATH` 环境变量 | 用户显式指定 |
| 2 | 内嵌便携版 `_internal/texlive/` | PyInstaller 打包后优先，避免系统版本不兼容 |
| 3 | 系统 PATH | 已安装 TeX Live / MiKTeX |

使用便携版时，编译分两步：
1. **xelatex -no-pdf** — 生成 XDV 中间文件
2. **xdvipdfmx** — 将 XDV 转为 PDF（设置 `DVIPDFMXINPUTS` 指向 `dvipdfmx.cfg`；macOS/Linux 上使用 `xdvipdfmx`，Windows 上使用 `xdvipdfmx.exe`）

两步法而非一步法的原因：Windows 上 xelatex 内部调用 xdvipdfmx 时，子进程可能无法正确继承环境变量，导致 `系统找不到指定的路径` 错误（xdvipdfmx 找不到 `dvipdfmx.cfg`）。

`shared/pdf_compiler.py` 通过环境变量向两个进程注入完整搜索路径：

- `TEXMFDIST` → 便携版 texmf-dist 绝对路径
- `TEXMFVAR` → 临时目录（避免写入只读打包树）
- `TEXMFCNF` → 便携版根目录 + web2c 配置
- `FONTCONFIG_PATH` / `FONTCONFIG_FILE` → 字体配置
- `TEXINPUTS` / `OPENTYPEFONTS` / `TFMFONTS` 等 → 各类文件搜索路径
- `DVIPDFMXINPUTS` → dvipdfmx 配置文件搜索路径（指向 `texmf-dist/dvipdfmx/`）

格式文件 `xelatex.fmt` 在每次编译前复制到临时 `TEXMFVAR` 目录。

## 字体策略

模板中三款字体均使用**开源替代**，通过 `.otf`/`.ttf` 扩展名触发 kpathsea 文件名查找（无需 fontconfig 缓存）：

| 用途 | 字体（开源） |
|---|---|
| CJK 正文（宋体） | FandolSong-Regular.otf |
| CJK 粗体 | FandolSong-Bold.otf |
| CJK 斜体 | FandolKai-Regular.otf |
| 拉丁正文 | texgyretermes-regular.otf |
| 符号回退 | DejaVuSans.ttf |

TeX Gyre Termes 默认启用 `Ligatures=TeX`，需要 `tex-text.tec` 字体映射文件。
模板已设置 `Ligatures=TeXOff` 去掉此依赖，同时便携版仍包含映射文件以防万一。

字体文件随 `bundled_texlive/` 一起打包，SIL OFL 许可证允许自由分发。

## 多学科打包

每个学科独立打包，生成独立的 exe 和目录：

```
dist/
  高中物理/
    高中物理.exe
    config.json
    _internal/
  高中语文/
    高中语文.exe
    config.json
    _internal/
  ...
```

每个学科的 `.spec` 文件结构相同，只需修改：
1. 入口文件路径（`高中物理/main.py` → `高中语文/main.py`）
2. exe 名称（`name='高中物理'` → `name='高中语文'`）
3. datas 中的学科配置路径

`bundled_texlive/` 和 `core/`、`shared/`、`ui/` 在各学科的 `_internal` 中各自有副本。如需减小总体积，可考虑将共享部分提取到公共目录（当前方案未做此优化，优先保证各学科完全独立）。

## 常见问题

**Q: 目标机器上没有 TeX Live 能生成 PDF 吗？**
可以。便携版包含完整的最小 TeX 发行版，无需额外安装。

**Q: 目标机器装了 TeX Live 会冲突吗？**
不会。有系统 TeX Live 时自动使用系统的（优先级更高），便携版不会被激活。

**Q: 如何更新便携 TeX？**
在本机更新 TeX Live 后，重新运行 `python tools/build_minimal_texlive.py`，再 `pyinstaller specs/高中物理.spec`。

**Q: 字体渲染效果和原来的 SimSun 一样吗？**
Fandol Song 是宋体风格，视觉上与 SimSun 基本一致。如需完全一致，可将模板字体改回 SimSun（但目标机器必须有该字体）。

**Q: 为什么 config.json 在 exe 同级而不是 _internal 里？**
方便用户手动编辑学科配置（提示词、拆分规则等）。`core/env_config.py` 和 `core/config_loader.py` 都支持从 exe 同级目录读取。

**Q: 每个学科都有一份 _internal 副本，会不会太大？**
约 200 MB/学科。如果学科数量多且体积敏感，可后续优化为：共享库放公共目录，各学科 exe 只放差异部分。当前优先保证独立性和简单性。

## 打包常见问题与解决办法

### 问题1：旧版学科（v1.x）与新版 UI（v3.x）接口不兼容

**现象**：
- 启动报错，提示缺少参数或方法签名不匹配
- UI 上缺少「分割方式」下拉框
- 工具调用失败，提示词中缺少工具说明

**原因**：
`ui/default_app.py` 升级到 v3.0 接口后，旧版学科的 `subject.py` 方法签名与新版不匹配：

| 方法 | v1.x 旧签名 | v3.x 新签名 |
|------|------------|------------|
| `split_lecture` | `(md_content, output_dir, subject_config)` | `(md_file, output_root, base_name, options=None)` |
| `split_exam` | `(md_content, output_dir, subject_config)` | `(md_file, output_root, base_name, options=None)` |
| `generate_knowledge` | `(md_content, output_dir, subject_config)` | 已废弃（ADR-0017），`()` 直接返回 False |
| `proofread_one` | `(api_cfg, q_dir, q_name, is_knowledge, generate_pdf)` | `(ctx: SessionContext, q_dir, q_name, generate_pdf, source_mode="试卷")` |
| `get_tool_instructions` | `(tools)` 需要传参 | `()` 无参，从 `self.tools` 生成 |
| `get_knowledge_prompt` | `()` 返回知识点提示词 | 已删除（ADR-0017），知识提取概念已废弃 |
| `get_ui_features` | 无此方法 | `()` 返回 UI 功能开关字典 |

**解决办法**：
升级学科的 `subject.py`，使其方法签名与 v3.0 兼容。可参考 `subjects/高中物理v3.0/subject.py` 或 `subjects/高中语文v3.0/subject.py` 的实现。

---

### 问题2：config.json 位置与预期不符

**现象**：
- 按照文档说 config.json 应该在 exe 同级，但打包后只在 `_internal` 里找到
- 用户无法方便地编辑配置

**原因**：
PyInstaller 的 datas 配置 `(src, '.')` 是将文件复制到 `_MEIPASS` 根目录（即 `_internal/`），而不是 exe 所在目录。

**解决办法**：
采用「内置默认配置 + 首次运行复制」策略：

1. spec 文件中照常把 `config.json` 打包到 `_internal/`（作为内置默认配置）
2. `main.py` 新增 `_get_subject_dir()` 函数，打包后返回 exe 所在目录
3. `main.py` 新增 `_ensure_config()` 函数，首次运行时检测 exe 同级是否有 `config.json`，没有则从内置资源复制
4. `SubjectApp` 使用 exe 同级目录作为 `subject_dir`（配置读取位置）

这样既保证开箱即用，又方便用户手动编辑配置。

---

### 问题3：spec 文件路径解析错误

**现象**：
从不同目录运行 `pyinstaller` 时，找不到项目文件。

**原因**：
使用 `sys.argv[0]` 来定位 spec 文件路径不可靠，在某些情况下路径不正确。

**解决办法**：
使用 PyInstaller 内置变量 `SPECPATH`，它始终指向当前 spec 文件所在目录的绝对路径：

```python
spec_file = os.path.abspath(SPECPATH)
project_root = os.path.dirname(spec_file)
```

---

### 问题4：运行时缺少模块（ModuleNotFoundError）

**现象**：
打包后运行报错，提示找不到某个模块（如 `shared.free_proofread`、`core.manual_split` 等）。

**原因**：
这些模块是通过动态导入或条件导入使用的，PyInstaller 无法自动检测到，需要手动加到 `hiddenimports`。

**解决办法**：
在 spec 文件的 `hiddenimports` 列表中添加缺失的模块。每次新增功能模块后，记得同步更新所有学科的 spec 文件。

---

### 问题5：app.py 路径 hack 脆弱

**现象**：
某些学科的 `app.py` 使用字符串替换方式设置 sys.path：
```python
sys.path.insert(0, sys.path[0].replace(r'subjects\\小学数学', ''))
```

**原因**：
这种方式依赖目录名和路径格式，不健壮，改名或移动目录就会失效。

**解决办法**：
使用 `os.path.dirname()` 逐层向上定位：
```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

---

### 问题6：打包体积过大

**现象**：
打包出来超过 300 MB。

**原因**：
PyInstaller 会把检测到的所有依赖都打包进去，包括一些没用到的大库（如 `matplotlib`、`scipy`、`numpy`）。

**解决办法**：
在 spec 文件的 `excludes` 中排除不需要的大库：
```python
excludes=['tests', 'pytest', 'matplotlib', 'scipy', 'numpy'],
```

排除后体积可减少约 50-100 MB。
