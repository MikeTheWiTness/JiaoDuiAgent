"""高中语文业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.web_tools import WebSearchTool
from core.config_loader import load_config
from core.defaults import (
    default_split_lecture,
    default_split_exam,
    default_generate_knowledge,
    default_proofread_one,
    default_collect_paper_dirs,
)

LEVEL = "高中"
SUBJECT = "语文"


class SubjectApp:
    name = "高中语文"
    version = "v1.1"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self):
        """构建高中语文专用工具集。语文用联网检索，不用计算工具。"""
        return [
            WebSearchTool(),
        ]

    def get_max_tool_loops(self):
        """工具调用最大循环次数。语文需要原文检索验证，次数较多。"""
        return 10

    def get_tool_instructions(self, tools):
        """生成工具使用指令。"""
        instructions = []
        for tool in tools:
            if tool.name == "web_search":
                instructions.append(
                    "web_search: 联网搜索工具。用于验证古诗文原文、文学常识、作者信息、"
                    "成语典故等语文知识的准确性。涉及原文引用、文学常识类题目，"
                    "必须用此工具检索验证，不得凭模型自身记忆判断。"
                )
        return "\n".join(instructions)

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