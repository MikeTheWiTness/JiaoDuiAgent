"""初中英语业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.base_subject import BaseSubjectApp
from core.defaults import (
    default_split_lecture,
)


class SubjectApp(BaseSubjectApp):
    LEVEL = "初中"
    SUBJECT = "英语"
    name = "初中英语"
    version = "v3.0"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)

    def build_tools(self):
        """构建初中英语专用工具集。英语以语法/词汇校对为主，无需计算工具。"""
        from shared.plan_tools import PlanUpdateTool
        return [PlanUpdateTool()]

    def get_max_tool_loops(self):
        """工具调用最大循环次数。"""
        return 15

    def get_tool_instructions(self):
        """生成工具使用指令。"""
        if not self.tools:
            return ""
        return "\n".join([f"- {t.name}" for t in self.tools])

    def get_question_prompt(self):
        """获取题目校对提示词。agent_prompt.json 为唯一来源，缺失时 fail-fast（ADR-00XX）。"""
        agent_lines = self.config.get("agent_prompt_lines")
        if not agent_lines:
            raise ValueError(
                "缺少 agent_prompt.json 或 agent_prompt_lines 为空，无法校对——请修复配置后重新发起校对")
        return "\n".join(agent_lines)

    def get_review_prompt(self):
        """获取批注评审提示词。"""
        agent_lines = self.config.get("agent_prompt_lines")
        if not agent_lines:
            raise ValueError(
                "缺少 agent_prompt.json 或 agent_prompt_lines 为空，无法校对——请修复配置后重新发起校对")
        return "\n".join(agent_lines)

    def split_lecture(self, md_file, output_root, base_name, options):
        if options is None:
            options = {}
        do_clean = options.get("do_clean", True)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)





