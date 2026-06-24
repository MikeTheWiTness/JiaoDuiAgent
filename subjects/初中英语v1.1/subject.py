"""初中英语业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
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

LEVEL = "初中"
SUBJECT = "英语"


class SubjectApp:
    name = "初中英语"
    version = "v1.1"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self):
        """构建初中英语专用工具集。英语以语法/词汇校对为主，无需计算工具。"""
        return []

    def get_max_tool_loops(self):
        """工具调用最大循环次数。英语无需工具调用。"""
        return 0

    def get_tool_instructions(self, tools):
        """生成工具使用指令。"""
        if not tools:
            return ""
        return "\n".join([f"- {t.name}" for t in tools])

    def get_question_prompt(self):
        """获取题目校对提示词。"""
        return "\n".join(self.config.get("question_prompt_lines", []))

    def get_knowledge_prompt(self):
        """获取知识提取提示词。"""
        return "\n".join(self.config.get("knowledge_prompt_lines", []))

    def split_lecture(self, md_content, output_dir, subject_config):
        return default_split_lecture(md_content, output_dir, subject_config)

    def split_exam(self, md_content, output_dir, subject_config):
        return default_split_exam(md_content, output_dir, subject_config)

    def generate_knowledge(self, md_content, output_dir, subject_config):
        return default_generate_knowledge(md_content, output_dir, subject_config)

    def proofread_one(self, api_cfg, q_dir, q_name, is_knowledge, generate_pdf):
        return default_proofread_one(
            self, api_cfg, q_dir, q_name, is_knowledge, generate_pdf
        )

    def collect_paper_dirs(self, base_dir):
        return default_collect_paper_dirs(base_dir)

    def pre_proofread_hook(self, md):
        return md

    def post_proofread_hook(self, result, question_data):
        return result