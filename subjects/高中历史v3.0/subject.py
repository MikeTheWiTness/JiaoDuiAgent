"""高中历史业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import load_config
from core.defaults import (
    default_split_lecture,
    default_split_exam,
    default_proofread_one,
    default_collect_paper_dirs,
)
from core.manual_split import split_by_manual_markers, split_by_unit_markers
from core.logging_utils import log
from core.base_subject import BaseSubjectApp
from shared.image_utils import copy_md_images
import shutil
import re
from pathlib import Path


class SubjectApp(BaseSubjectApp):
    LEVEL = "高中"
    SUBJECT = "历史"
    name = "高中历史"
    version = "v3.0"
    _show_knowledge_option = False
    _clean_bold_replacement = r"\1"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)
        self._react_mode = False

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

    def split_lecture(self, md_file, output_root, base_name, options):
        from shared.decor_utils import strip_decor_images
        from shared.split_post_utils import mark_navigation_units

        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")
        do_clean = options.get("do_clean", True)

        if split_mode == "rule":
            # 预清洗：去除装饰图片
            result = default_split_lecture(md_file, output_root, base_name, do_clean, self.config)
            # 后处理：删除导航/封面板块
            if result:
                mark_navigation_units(output_root, base_name)
            return result

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 预清洗：去除装饰图片
        md_content = strip_decor_images(md_content)

        if split_mode == "none":
            problems = [{"content": md_content}]
        elif split_mode == "manual":
            problems = split_by_unit_markers(md_content)
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




