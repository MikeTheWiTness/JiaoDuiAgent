"""初中英语业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
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
from core.manual_split import split_by_manual_markers
from core.logging_utils import log
from core.base_subject import BaseSubjectApp
from shared.image_utils import copy_md_images
import shutil
import re
from pathlib import Path


class SubjectApp(BaseSubjectApp):
    LEVEL = "初中"
    SUBJECT = "英语"
    name = "初中英语"
    version = "v3.0"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)
        self._react_mode = False

    def build_tools(self):
        """构建初中英语专用工具集。英语以语法/词汇校对为主，无需计算工具。"""
        base = []
        if self.react_mode:
            from shared.plan_tools import PlanUpdateTool
            from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool
            base.append(PlanUpdateTool())
            base.append(LocateParagraphTool())
            base.append(ReadSectionTool())
        return base

    def get_max_tool_loops(self):
        """工具调用最大循环次数。"""
        return 15 if self.react_mode else 0

    def get_tool_instructions(self):
        """生成工具使用指令。"""
        if not self.tools:
            return ""
        return "\n".join([f"- {t.name}" for t in self.tools])

    def get_question_prompt(self):
        """获取题目校对提示词。ReAct 模式时优先用 agent_prompt。"""
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                return "\n".join(agent_lines)
        return "\n".join(self.config.get("question_prompt_lines", []))

    def get_review_prompt(self):
        """获取批注评审提示词。"""
        from shared.review_mode import build_review_prompt
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                return "\n".join(agent_lines)
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        return base_prompt + "\n\n" + build_review_prompt("")

    def split_lecture(self, md_file, output_root, base_name, options):
        if options is None:
            options = {}
        do_clean = options.get("do_clean", True)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)





