"""高中历史业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
from shared.image_utils import copy_md_images
import shutil
import re
from pathlib import Path


class SubjectApp:
    LEVEL = "高中"
    SUBJECT = "历史"
    name = "高中历史"
    version = "v3.0"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self._react_mode = False
        self.tools = self.build_tools()

    @property
    def react_mode(self):
        return self._react_mode

    @react_mode.setter
    def react_mode(self, value):
        self._react_mode = value
        self.tools = self.build_tools()

    def build_tools(self):
        base = []
        if self.react_mode:
            from shared.plan_tools import PlanUpdateTool
            from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool
            base.append(PlanUpdateTool(nudge_template=""))
            base.append(LocateParagraphTool())
            base.append(ReadSectionTool())
        return base

    def get_max_tool_loops(self):
        return 15 if self.react_mode else 0

    def get_tool_instructions(self):
        # 历史学科不需要联网检索工具（史实主要靠 LLM 自身知识）
        # ReAct 模式下仅提供 plan_update、locate_paragraph、read_section
        return ""

    def get_question_prompt(self):
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                return "\n".join(agent_lines)
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        return base_prompt

    def get_knowledge_prompt(self):
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                return "\n".join(agent_lines)
        base_prompt = "\n".join(self.config.get("knowledge_prompt_lines", []))
        return base_prompt


    def split_lecture(self, md_file, output_root, base_name, options):
        from shared.decor_utils import strip_decor_images, strip_decor_images_from_file
        from shared.split_post_utils import remove_navigation_units

        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")
        do_clean = options.get("do_clean", True)

        if split_mode == "rule":
            # 预清洗：去除装饰图片
            strip_decor_images_from_file(str(md_file))
            result = default_split_lecture(md_file, output_root, base_name, do_clean, self.config)
            # 后处理：删除导航/封面板块
            if result:
                remove_navigation_units(output_root, base_name)
            return result

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 预清洗：去除装饰图片
        md_content = strip_decor_images(md_content)

        if split_mode == "none":
            problems = [{"content": md_content}]
        elif split_mode == "manual":
            problems = split_by_manual_markers(md_content)
        elif split_mode == "knowledge_manual":
            from core.manual_split import split_by_knowledge_markers
            problems = split_by_knowledge_markers(md_content)
        elif split_mode == "knowledge_smart":
            api_url = options.get("api_url", "")
            api_key = options.get("api_key", "")
            model = options.get("model", "")
            from shared.knowledge_split import knowledge_split_smart
            problems = knowledge_split_smart(md_content, api_url, api_key, model, md_file=md_file)
        elif split_mode == "smart":
            api_url = options.get("api_url", "")
            api_key = options.get("api_key", "")
            model = options.get("model", "")
            from shared.smart_split import smart_split
            problems = smart_split(md_content, api_url, api_key, model, md_file=md_file)
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
            problems = smart_split(md_content, api_url, api_key, model, md_file=md_file)
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

            img_result = copy_md_images(content, [src_media, md_dir], img_dir)
            new_content = img_result.content

            (q_dir / f"第{idx}题.md").write_text(new_content, encoding='utf-8')

            # 同步生成 _clean.md（去除所有格式标记的纯文本版）
            try:
                from shared.docx_format_enhancer import strip_format_markers
                clean = strip_format_markers(new_content)
                clean = re.sub(r'<批注\s+id=\d+>.*?</批注>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)
                clean = re.sub(r'__([^_]+)__', r'\1', clean)
                (q_dir / f"第{idx}题_clean.md").write_text(clean, encoding='utf-8')
            except Exception:
                pass

        log(f"📂 拆分完成: {len(problems)} 题")
        return True

    def generate_knowledge(self, md_file, output_root, base_name):
        return default_generate_knowledge(md_file, output_root, base_name, self.config)

    def get_review_prompt(self):
        from shared.review_mode import build_review_prompt
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                base_prompt = "\n".join(agent_lines)
                return base_prompt
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        review_specific = build_review_prompt("")
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
            prompt, self.tools, self.get_max_tool_loops(), generate_pdf,
            react_mode=self.react_mode
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

    def pre_proofread_hook(self, md_text, api_url=None, api_key=None, model=None, q_dir=None):
        # 历史学科不需要前置原文检索
        return md_text

    def post_proofread_hook(self, result, q_dir):
        return result

    def get_ui_features(self):
        return {
            "show_clean_table_option": True,
            "show_knowledge_option": False,
            "show_pdf_option": True,
            "show_parallel_option": True,
            "show_source_modes": ["讲义", "试卷", "自由校对", "批注评审"],
            "show_exec_modes": ["完整流程", "仅转换", "仅拆分", "仅校对", "仅生成PDF"],
            "show_split_mode_option": True,
            "add_file_title": "添加文件",
            "add_folder_title": "添加文件夹",
        }
