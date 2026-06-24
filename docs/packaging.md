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

每个学科对应一个 `.spec` 文件，放在 `specs/` 目录下。以高中物理为例：

```python
# specs/高中物理.spec
import os
import sys

spec_file = sys.argv[0]
project_root = os.path.dirname(os.path.dirname(os.path.abspath(spec_file)))
sys.path.insert(0, project_root)

a = Analysis(
    [os.path.join(project_root, '高中物理/main.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, '高中物理/config.json'), '.'),
        (os.path.join(project_root, '高中物理/subject.py'), '.'),    # 学科模块
        (os.path.join(project_root, '高中物理/app.py'), '.'),         # 应用模块
        (os.path.join(project_root, 'shared/templates'), 'templates'),
        (os.path.join(project_root, 'bundled_texlive'), 'texlive'),
    ],
    hiddenimports=[
        'core', 'core.paths', 'core.parsing', 'core.api_client',
        'core.pandoc_utils', 'core.env_config', 'core.logging_utils',
        'core.config_loader', 'core.defaults',
        'shared.sympy_tools', 'shared.sympy_tools.tools',
        'shared.sympy_tools.templates', 'shared.sympy_tools.sandbox',
        'shared.sympy_tools.safety',
        'shared.web_tools', 'shared.latex_generator', 'shared.pdf_compiler',
        'ui', 'ui.widgets', 'ui.default_app',
        'pydantic', 'langchain_core', 'langchain_core.tools',
    ],
    excludes=['tests', 'pytest'],
    ...
)

exe = EXE(
    ...
    name='高中物理',
    console=False,
    ...
)
```

### 关键配置要点

1. **动态路径解析**：spec 文件开头的路径计算确保无论从哪个目录执行 PyInstaller，都能正确定位项目文件。

2. **必需的 datas 配置**：除了 `config.json`，还必须包含 `subject.py` 和 `app.py`，因为 `main.py` 通过 `importlib.util` 动态加载这两个模块。

3. **打包后路径处理**：`main.py` 中需使用 `sys._MEIPASS` 来定位打包后的资源文件：

```python
def _get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstaller 临时目录
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

subject_mod = _load_module("subject", _get_resource_path("subject.py"))
app_mod = _load_module("app", _get_resource_path("app.py"))
```

4. **hiddenimports**：必须列出 `core/`、`shared/`、`ui/` 的所有子模块，因为它们是动态导入的，PyInstaller 无法自动检测。

## 运行时 xelatex 发现机制

`shared/pdf_compiler.py` 按以下优先级查找 xelatex：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `XELATEX_PATH` 环境变量 | 用户显式指定 |
| 2 | 内嵌便携版 `_internal/texlive/` | PyInstaller 打包后优先，避免系统版本不兼容 |
| 3 | 系统 PATH | 已安装 TeX Live / MiKTeX |

使用便携版时，编译分两步：
1. **xelatex -no-pdf** — 生成 XDV 中间文件
2. **xdvipdfmx** — 将 XDV 转为 PDF（设置 `DVIPDFMXINPUTS` 指向 `dvipdfmx.cfg`）

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
