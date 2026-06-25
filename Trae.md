# Trae.md

This file provides guidance to Trae AI when working with code in this repository.

## Project Overview

K-12 multi-subject AI proofreading toolkit — **each subject is a standalone program** with its own business logic and UI. Shared layers (`core/`, `shared/`, `ui/`) provide only pure utilities and default templates. Subjects can reuse or completely override them.

**Key design principle**: Subjects own their business logic and UI. Shared layers have zero subject-specific code.

## Commands

```bash
# Create and activate venv (Python 3.12)
py -3.12 -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run 高中物理
python 高中物理/main.py

# Run another subject
python 高中语文/main.py

# Package to EXE (高中物理 example)
pip install pyinstaller
python tools/build_minimal_texlive.py  # once, or after TeX updates
pyinstaller specs/高中物理.spec
```

## Architecture

### Three-Layer Subject Separation

Each subject directory has 3 core files with clear separation of concerns:

| File | Responsibility | Customizable |
|------|---------------|-------------|
| `subject.py` | Business logic (tools, prompts, splitting, proofreading, hooks) | Fully custom or reuse `core/defaults` |
| `app.py` | GUI interface | Fully custom or inherit `ui.default_app.DefaultApp` |
| `main.py` | Entry point (assembles subject + app) | Barely needs changes |

### Directory Structure

```
校对agent/
├── core/                     # Pure utility layer (NO business logic, NO UI)
│   ├── paths.py              # Path utilities (frozen-compatible)
│   ├── parsing.py            # LLM output parsing (Markdown annotation markers)
│   ├── api_client.py         # API calls (HTTP, retry, tool loop) — max_loops parameterized
│   ├── pandoc_utils.py       # Pandoc docx→md conversion
│   ├── env_config.py         # .env read/write (accepts subject_dir param)
│   ├── logging_utils.py      # Thread-safe logging (set_log_func / log)
│   ├── config_loader.py      # config.json loader + accessor functions
│   └── defaults.py           # Default split + proofreading implementations (reference, not mandatory)
├── shared/                   # Shared tool libraries
│   ├── sympy_tools/          # Symbolic computation tools (10 tools)
│   │   ├── tools.py          # Tool definitions (EvaluateExpressionTool etc.)
│   │   ├── templates.py      # Code templates
│   │   ├── sandbox.py        # Subprocess sandbox execution
│   │   └── safety.py         # Dangerous code detection
│   ├── web_tools.py          # Web search / fetch utilities
│   ├── latex_generator.py    # Markdown → LaTeX (paracol two-column layout)
│   ├── pdf_compiler.py       # XeLaTeX PDF compilation (portable TeX support)
│   └── templates/
│       └── proofread_template.tex
├── ui/                       # UI component library + default template
│   ├── widgets.py            # Reusable components: LogPanel, ApiDialog, ModeSelector
│   └── default_app.py        # DefaultApp — default GUI template (inheritable)
├── 高中物理/                  # Example: standalone subject program
│   ├── main.py               # Entry point
│   ├── subject.py            # SubjectApp class (business logic)
│   ├── app.py                # SubjectGui class (UI, inherits DefaultApp)
│   ├── config.json           # Prompts + split rules
│   └── .env                  # API config (generated at runtime)
├── specs/                    # PyInstaller spec files (one per subject)
├── tools/
│   └── build_minimal_texlive.py
├── docs/
│   └── packaging.md
├── requirements.txt
└── Trae.md                   # This file
```

## Key Design Decisions (DO NOT VIOLATE)

1. **`core/` contains NO subject-specific logic.** No `if subject == "语文"` branches. No hardcoded tool mappings for specific subjects. `api_client.py` accepts `max_loops` as a parameter, it does NOT compute it from a subject name.

2. **`subject.py` owns all business logic.** Tools, prompt instructions, tool call limits, split logic, proofreading flow, hooks — all defined in the subject's own `subject.py`. The subject can reuse `core/defaults` but can also completely replace any of it.

3. **`app.py` owns the UI.** Each subject has its own GUI. `ui/default_app.py` is a reference template (inheritable), not a shared monolith. `ui/widgets.py` provides reusable building blocks.

4. **Subject directories are autonomous.** Adding a new subject = creating a new directory with `main.py` + `subject.py` + `app.py` + `config.json`. Zero changes to `core/`, `shared/`, or `ui/`.

5. **Chinese directory names for subjects.** Subjects use Chinese names (e.g., `高中物理/`). `main.py` loads `subject.py` and `app.py` via `importlib.util.spec_from_file_location` by file path, not by module name. `core/`, `shared/`, `ui/` use English names and normal imports.

6. **Independent `.env` per subject.** Each subject has its own `.env` in its own directory. `core.env_config` accepts `subject_dir` as a parameter.

7. **`core/defaults.py` is reference, not mandate.** Subjects may import from it, but modifying defaults does NOT break subjects that have customized their own implementations.

## SubjectApp Interface

Each `subject.py` must define a `SubjectApp` class with these methods:

```python
class SubjectApp:
    name: str                          # Display name (e.g. "高中物理")

    def __init__(self, subject_dir):   # subject_dir = path to this subject's folder
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self) -> list:     # List of tool instances
    def get_max_tool_loops(self) -> int
    def get_tool_instructions(self) -> str
    def get_question_prompt(self) -> str
    def get_knowledge_prompt(self) -> str

    # Splitting
    def split_lecture(self, md_file, output_root, base_name, options)
    def split_exam(self, md_file, output_root, base_name)
    def generate_knowledge(self, md_file, output_root, base_name)

    # Proofreading
    def proofread_one(self, api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf)
    def collect_paper_dirs(self, base_path) -> list

    # Hooks (default: no-op)
    def pre_proofread_hook(self, md_text) -> str
    def post_proofread_hook(self, result, q_dir): return result
```

## DefaultApp Extension Points

Subjects inheriting `DefaultApp` can override these methods for UI customization:

| Method | Purpose |
|--------|---------|
| `setup_extra_options(frame)` | Add subject-specific widgets to the options area |
| `on_start_proofread()` | Called when proofreading starts; read custom UI state and pass to subject_app |
| `on_start_conversion()` | Called when conversion starts |

For deeper customization, subjects can completely rewrite `app.py` without inheriting.

## Pipeline (Standard Flow)

### 1. Source input
Word `.docx` files — two sources:
- **Exam papers** — question banks with answers inline or at end
- **Lecture materials** — teaching content with examples and knowledge sections

### 2. Conversion & splitting

**Lecture mode:**
1. Pandoc `.docx` → `.md` with `--mathjax`
2. `fix_latex_escapes()` — remedy Pandoc over-escaping
3. `comprehensive_clean()` — strip table borders, merge split answer lines
4. Two split modes (from config):
   - **title mode**: split by bold patterns → `第N题/` directories
   - **section mode**: split by `##` headers → `板块N/` directories
5. `generate_knowledge_with_images()` — extract non-question sections → `知识/` (skipped in section mode)

**Exam mode:**
1. Pandoc `.docx` → `.md` (no `--mathjax`)
2. Post-process Microsoft formula format
3. `detect_answer_mode()` — `"inline"` or `"end"`
4. Parse end-of-document answer tables, inject `【答案】` lines
5. Split by `数字．` pattern → `第N题/` directories

### 3. Standard intermediate structure

```
paper_dir/
  第1题/
    第1题.md
    images/
  第2题/
    第2题.md
    images/
  ...
  知识/                     # lecture title mode only
    讲义名_知识.md
    images/
```

### 4. API proofreading
- Scans for question and knowledge folders
- Uses subject-specific prompts + tools
- Sends content + base64 images to LLM API
- `call_api()` — `reasoning_effort: "high"`, 2 retries, 480s timeout
- Tool call loop with subject-defined `max_loops`
- Interrupt/resume support — saves `_校对报告.md` per question immediately
- Markdown output format with numbered annotation markers

### 5. Report generation
- Per-exam Markdown report: `{name}_校对报告.md`
- Optional LaTeX PDF — two-column paracol layout (left: original, right: corrections)
- XeLaTeX compilation with CJK support

## Configuration

### config.json (per subject)

```json
{
  "question_prompt_lines": [...],
  "knowledge_prompt_lines": [...],
  "lecture_split": {
    "split_mode": "title" | "section",
    "section_pattern": "^##\\s",
    "wrapped_patterns": [...],
    "unwrapped_patterns": [...],
    "section_boundary": true
  },
  "exam_split": { "question_pattern": "^(\\d+)．" }
}
```

### .env (per subject)

```
API_URL=...
API_KEY=...
MODEL_NAME=...
```

Managed via GUI's API config dialog.

## Working with the Code

### Adding a new subject

1. Create `{学科名}/` directory
2. Create `config.json` with prompts and split rules
3. Create `subject.py` implementing `SubjectApp` class
4. Create `app.py` with `SubjectGui` class (inherit `DefaultApp` or write from scratch)
5. Create `main.py` (copy from 高中物理, basically unchanged)
6. Create `specs/{学科名}.spec` for packaging
7. **Do NOT modify** `core/`, `shared/`, or `ui/` unless you're adding truly subject-agnostic utilities

### Modifying defaults

`core/defaults.py` contains reference implementations extracted from the original codebase. Subjects that haven't customized their logic rely on it. When modifying defaults:
- Don't change function signatures (would break subjects calling them)
- Add new functions rather than changing behavior of existing ones
- Remember: subjects that have fully customized their logic don't import from defaults at all

### GUI changes

- For all-subject changes: modify `ui/default_app.py` or `ui/widgets.py`
- For single-subject changes: modify that subject's `app.py` (override methods or add widgets)
- Never add subject-specific code to `ui/default_app.py`

## Conventions

- **Language**: Variable and function names in English. Comments in Chinese are acceptable where the original code has them.
- **No comments in new code** unless explicitly requested.
- **Relative imports** inside `shared/sympy_tools/` (e.g. `from .safety import`).
- **Chinese subject directories** use `importlib.util.spec_from_file_location` to load modules by path.
- **Thread safety**: `core.logging_utils.log()` uses `_log_lock`. GUI updates must use `root.after()`.
- **Subprocess calls** on Windows use `CREATE_NO_WINDOW` flag to avoid black console windows.

---

## Knowledge Base

### Web Tools Guide

`shared/web_tools.py` provides two LangChain tools for web access.

#### Available Tools

| Tool | Name | Purpose |
|------|------|---------|
| `WebSearchTool` | `web_search` | Search the internet, return title/snippet/url list |
| `WebFetchTool` | `web_fetch` | Fetch and extract text from a specific URL |

#### Dedicated Website Adaptors

WebFetchTool has special handling for certain sites. Always prefer using the dedicated adaptor over generic fetching — better accuracy and reliability.

| Website | Adaptor | URL Pattern | Notes |
|---------|---------|-------------|-------|
| 搜韵网 (sou-yun.cn) | `_fetch_souyun` | `https://sou-yun.cn/QueryPoem.aspx?q=诗句` | ASP.NET form-based, handles `__VIEWSTATE`. Use `q` query param for poem lookup. Best for classical Chinese poetry verification. |
| 识典古籍 (shidianguji.com) | `_fetch_shidianguji` | `https://www.shidianguji.com/search/关键词` | Server-rendered HTML. Search URL encodes query in path. Best for classical prose/text verification. |
| Generic webpages | `_fetch_generic` | Any URL | Fallback. Quality varies depending on page structure. |

#### Usage Tips

- **For classical Chinese poetry verification**: use `web_fetch` with sou-yun.cn URL
- **For classical prose (文言文) verification**: use `web_fetch` with shidianguji.com URL
- **For general knowledge lookup**: use `web_search` first, then `web_fetch` on promising URLs
- `web_search` backends: `ddgs` (DuckDuckGo, international) or `baidu` (Chinese content best)
- Both tools return error messages in Chinese on failure — LLM should fall back to its own knowledge

### Chinese (语文) v2.0 Project

Major project under development. Upgrades 高中语文 from v1.1 to v2.0 with significant new features.

- **Project directory**: `subjects/高中语文v1.1/`
- **Task list**: `subjects/高中语文v1.1/docs/TASKS.md` (12 slices, start here to see current progress)
- **PRD**: `subjects/高中语文v1.1/docs/PRD_v2.0.md`
- **Architecture decisions**: `subjects/高中语文v1.1/docs/adr/` (8 ADRs)
- **GitHub issues**: https://github.com/MikeTheWiTness/JiaoDuiAgent/issues (issues #3-#14)

**New features in v2.0**:
- 自由校对 mode (free-form input: paste text + images, or upload files)
- 批注评审 mode (review human annotations in Word documents)
- Smart splitting via LLM with `<problem>` XML markers
- Manual marker-based splitting (`###### 题目开始 ######` / `###### 题目结束 ######`)
- Pre-proofreading classical text search + automatic diff (文言文/诗歌)
- All four source modes: 讲义 / 试卷 / 自由校对 / 批注评审

### Testing

**Status**: No formal test framework yet. Tests live in the project root as standalone scripts.

**Current test files**:
- `test_comments.py` — Word comment extraction test
- `test_shidianguji.py` — Shidianguji fetching test

**Running tests**:
```bash
# Run individual test scripts directly
python test_comments.py
python test_shidianguji.py
```

**Convention**: New test scripts go in the project root and are named `test_*.py`. Each test should be self-contained and print pass/fail results.

### Core File Quick Reference

| File | What it does | Touch when |
|------|-------------|------------|
| `core/defaults.py` | Default split + proofreading implementations (reference, not mandate) | Adding subject-agnostic default behaviors |
| `core/api_client.py` | API calls + tool call loop | Changing API behavior, retry logic, tool loop |
| `core/config_loader.py` | config.json loading and access | Adding new config fields |
| `shared/web_tools.py` | Web search and fetching tools | Adding new website adaptors, changing search backends |
| `shared/latex_generator.py` | Markdown → LaTeX PDF generation (two-column paracol) | Adding new PDF layouts, customizing template |
| `shared/pdf_compiler.py` | XeLaTeX compilation | Changing TeX paths, compilation options |
| `ui/default_app.py` | Default GUI template | Adding all-subject UI features, new source modes |
| `ui/widgets.py` | Reusable UI components | New shared widgets |
