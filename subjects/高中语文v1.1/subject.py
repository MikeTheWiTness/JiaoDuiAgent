"""高中语文业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.web_tools import WebSearchTool, WebFetchTool
from core.config_loader import load_config
from core.defaults import (
    default_split_lecture,
    default_split_exam,
    default_generate_knowledge,
    default_proofread_one,
    default_collect_paper_dirs,
)
from core.manual_split import split_by_manual_markers
from core.logging_utils import log
import shutil
import re
from pathlib import Path


class SubjectApp:
    LEVEL = "高中"
    SUBJECT = "语文"
    name = "高中语文"
    version = "v2.0"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self):
        return [
            WebSearchTool(),
            WebFetchTool(),
        ]

    def get_max_tool_loops(self):
        return 10

    def get_tool_instructions(self):
        web_tools = [t for t in self.tools if t.name == "web_search" or t.name == "web_fetch"]

        lines = []
        if web_tools:
            lines.append("## 可用的联网搜索工具\n"
                "如需查找最新说法、验证专业术语、检索不在训练数据内的信息，可使用：\n")
            lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in web_tools))
            lines.append(
                "\n使用规则：\n"
                "1. 涉及古诗文原文、作者信息、文学常识等，**优先使用 web_fetch 访问识典古籍**（权威来源）。\n"
                "   - 文言文/古文：调用 `web_fetch` 访问 https://www.shidianguji.com/search/关键词\n"
                "   - 古诗词/诗歌：调用 `web_fetch` 访问 https://sou-yun.cn/QueryPoem.aspx?q=诗句\n"
                "2. 识典古籍或搜韵网找不到时，再用 web_search 全网搜索。\n"
                "3. 成语典故、现代文知识点等，可直接用 web_search 验证。\n"
                "4. 不得凭模型自身记忆判断古诗文原文，必须通过工具检索验证。\n"
            )

        return "".join(lines)

    def get_question_prompt(self):
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def get_knowledge_prompt(self):
        base_prompt = "\n".join(self.config.get("knowledge_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def split_lecture(self, md_file, output_root, base_name, options):
        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")
        do_clean = options.get("do_clean", True)

        if split_mode == "rule":
            return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        if split_mode == "none":
            problems = [{"content": md_content}]
        elif split_mode == "manual":
            problems = split_by_manual_markers(md_content)
        elif split_mode == "smart":
            api_url = options.get("api_url", "")
            api_key = options.get("api_key", "")
            model = options.get("model", "")
            from shared.smart_split import smart_split
            problems = smart_split(md_content, api_url, api_key, model)
        else:
            log(f"⚠️ 未知分割模式: {split_mode}，使用规则模式")
            return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)

        return self._write_problems_to_dirs(md_file, output_root, base_name, problems)

    def split_exam(self, md_file, output_root, base_name, options=None):
        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")

        if split_mode == "rule":
            return default_split_exam(md_file, output_root, base_name, self.config)

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        if split_mode == "none":
            problems = [{"content": md_content}]
        elif split_mode == "manual":
            problems = split_by_manual_markers(md_content)
        elif split_mode == "smart":
            api_url = options.get("api_url", "")
            api_key = options.get("api_key", "")
            model = options.get("model", "")
            from shared.smart_split import smart_split
            problems = smart_split(md_content, api_url, api_key, model)
        else:
            log(f"⚠️ 未知分割模式: {split_mode}，使用规则模式")
            return default_split_exam(md_file, output_root, base_name, self.config)

        return self._write_problems_to_dirs(md_file, output_root, base_name, problems)

    def _write_problems_to_dirs(self, md_file, output_root, base_name, problems):
        if not problems:
            log("⚠️ 没有题目可写入")
            return False

        md_dir = Path(md_file).parent
        src_media = md_dir / f"{base_name}_images" / "media"
        target_root = Path(output_root) / base_name
        target_root.mkdir(parents=True, exist_ok=True)

        for idx, prob in enumerate(problems, start=1):
            content = prob.get("content", "")
            q_dir = target_root / f"第{idx}题"
            q_dir.mkdir(exist_ok=True)
            img_dir = q_dir / "images"
            img_dir.mkdir(exist_ok=True)

            img_pat = re.compile(r'!\[(.*?)\]\((.*?)\)')
            def _copy_img(m):
                alt, src = m.group(1), m.group(2).strip()
                if src.startswith('http://') or src.startswith('https://'):
                    return m.group(0)
                img_name = Path(src).name
                src_path = None
                candidates = [
                    src_media / img_name,
                    md_dir / src,
                    md_dir / Path(src).name,
                ]
                for cand in candidates:
                    try:
                        if cand.exists() and cand.is_file():
                            src_path = cand
                            break
                    except Exception:
                        pass
                if src_path:
                    dest = img_dir / img_name
                    if not dest.exists():
                        try:
                            shutil.copy2(src_path, dest)
                        except Exception:
                            pass
                    return f"![{alt}](./images/{img_name})"
                return m.group(0)
            new_content = img_pat.sub(_copy_img, content)

            (q_dir / f"第{idx}题.md").write_text(new_content, encoding='utf-8')

        log(f"📂 拆分完成: {len(problems)} 题")
        return True

    def generate_knowledge(self, md_file, output_root, base_name):
        return default_generate_knowledge(md_file, output_root, base_name, self.config)

    def get_review_prompt(self):
        from shared.review_mode import build_review_prompt
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        review_specific = build_review_prompt("")
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions + "\n\n" + review_specific
        return base_prompt + "\n\n" + review_specific

    def proofread_one(self, api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf, source_mode="试卷"):
        if is_knowledge:
            prompt = self.get_knowledge_prompt()
        elif source_mode == "批注评审":
            prompt = self.get_review_prompt()
        else:
            prompt = self.get_question_prompt()
        return default_proofread_one(
            api_url, api_key, model, q_dir, q_name, is_knowledge,
            prompt, self.tools, self.get_max_tool_loops(), generate_pdf
        )

    def collect_paper_dirs(self, base_path):
        return default_collect_paper_dirs(base_path)

    def get_supported_file_types(self):
        return [
            ("支持的文件", "*.docx;*.doc;*.md;*.zip"),
            ("Word 文档", "*.docx;*.doc"),
            ("Markdown 文件", "*.md"),
            ("ZIP 压缩包", "*.zip"),
            ("所有文件", "*.*"),
        ]

    def get_supported_extensions(self):
        return {".docx", ".doc", ".md"}

    def pre_proofread_hook(self, md_text):
        from shared.chinese_classics_tools import preprocess_for_proofread
        return preprocess_for_proofread(md_text)

    def post_proofread_hook(self, result, q_dir):
        return result

    def get_ui_features(self):
        return {
            "show_clean_table_option": True,
            "show_knowledge_option": True,
            "show_pdf_option": True,
            "show_parallel_option": True,
            "show_source_modes": ["讲义", "试卷", "自由校对", "批注评审"],
            "show_exec_modes": ["完整流程", "仅转换", "仅拆分", "仅校对", "仅生成PDF"],
            "show_split_mode_option": True,
            "add_file_title": "添加文件",
            "add_folder_title": "添加文件夹",
        }
