"""高中化学业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.sympy_tools.tools import (
    EvaluateExpressionTool,
    SolveEquationTool,
    CheckEqualityTool,
    SimplifyExpressionTool,
    BalanceChemicalEquationTool,
    StoichiometryCalcTool,
)
from shared.web_tools import WebSearchTool
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
    LEVEL = "高中"
    SUBJECT = "化学"
    name = "高中化学"
    version = "v3.0"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)
        self._react_mode = False

    def build_tools(self):
        """构建高中化学专用工具集。"""
        base = [
            EvaluateExpressionTool(),
            SolveEquationTool(),
            CheckEqualityTool(),
            SimplifyExpressionTool(),
            BalanceChemicalEquationTool(),
            StoichiometryCalcTool(),
            WebSearchTool(),
        ]
        if self.react_mode:
            from shared.plan_tools import PlanUpdateTool
            from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool
            from shared.chemistry_tools import ChemistryIndependentSolveTool
            # 化学 nudge 置空：自检靠 prompt 第 8 步，不依赖工具 nudge（对标 ADR-0006 决策 2）
            base.append(PlanUpdateTool(nudge_template=""))
            base.append(LocateParagraphTool())
            base.append(ReadSectionTool())
            base.append(ChemistryIndependentSolveTool())
        return base

    def get_max_tool_loops(self):
        """工具调用最大循环次数。"""
        return 30 if self.react_mode else 20

    def get_tool_instructions(self):
        """生成工具使用指令（自动从工具描述生成，对标物理结构化风格）。"""
        sympy_tools = [t for t in self.tools if t.name not in ("web_search", "web_fetch",
                         "plan_update", "locate_paragraph", "read_section", "independent_solve")]
        web_tools = [t for t in self.tools if t.name == "web_search" or t.name == "web_fetch"]

        lines = []

        if sympy_tools:
            lines.append("## 可用的化学计算工具\n"
                "你在校对该学科题目时，可以使用以下工具进行**实算验证**，不得凭模型自身估算数值结果：\n")
            lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in sympy_tools))
            lines.append("\n使用规则：对于需要化学方程式配平、化学计量计算、数值计算、方程求解的步骤，必须调用对应工具获取精确结果。\n")

        if web_tools:
            lines.append("## 可用的联网搜索工具\n"
                "如需查找最新物质性质、反应条件、不在训练数据内的化学信息，可使用：\n")
            lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in web_tools))
            lines.append("\n使用规则：先调 web_search 搜索，若需查看详情页再调 web_fetch 抓取。"
                "搜索失败或超时是正常情况，此时使用模型自身知识继续。\n")

        return "\n".join(lines)

    def get_question_prompt(self):
        """获取题目校对提示词。ReAct 模式时优先用 agent_prompt。"""
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                base_prompt = "\n".join(agent_lines)
                tool_instructions = self.get_tool_instructions()
                if tool_instructions:
                    return base_prompt + "\n\n" + tool_instructions
                return base_prompt
        return "\n".join(self.config.get("question_prompt_lines", []))

    def get_review_prompt(self):
        """获取批注评审提示词。"""
        from shared.review_mode import build_review_prompt
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                base_prompt = "\n".join(agent_lines)
                tool_instructions = self.get_tool_instructions()
                if tool_instructions:
                    return base_prompt + "\n\n" + tool_instructions
                return base_prompt
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        review_specific = build_review_prompt("")
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions + "\n\n" + review_specific
        return base_prompt + "\n\n" + review_specific

    def split_lecture(self, md_file, output_root, base_name, options):
        if options is None:
            options = {}
        do_clean = options.get("do_clean", True)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)




