"""高中化学业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.base_subject import BaseSubjectApp
from core.defaults import (
    default_split_lecture,
)
from shared.sympy_tools.tools import (
    BalanceChemicalEquationTool,
    CheckEqualityTool,
    EvaluateExpressionTool,
    SimplifyExpressionTool,
    SolveEquationTool,
    StoichiometryCalcTool,
)
class SubjectApp(BaseSubjectApp):
    LEVEL = "高中"
    SUBJECT = "化学"
    name = "高中化学"
    version = "v3.0"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)

    def build_tools(self):
        """构建高中化学专用工具集。"""
        base = [
            EvaluateExpressionTool(),
            SolveEquationTool(),
            CheckEqualityTool(),
            SimplifyExpressionTool(),
            BalanceChemicalEquationTool(),
            StoichiometryCalcTool(),
        ]
        from shared.chemistry_tools import ChemistryIndependentSolveTool
        from shared.plan_tools import PlanUpdateTool
        # 化学 nudge 置空：自检靠 prompt 第 8 步，不依赖工具 nudge（对标 ADR-0006 决策 2）
        base.append(PlanUpdateTool(nudge_template=""))
        base.append(ChemistryIndependentSolveTool())
        return base

    def get_max_tool_loops(self):
        """工具调用最大循环次数。"""
        return 30

    def get_tool_instructions(self):
        """生成工具使用指令（自动从工具描述生成，对标物理结构化风格）。"""
        sympy_tools = [t for t in self.tools if t.name not in ("web_search", "web_fetch",
                         "plan_update", "independent_solve")]
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
        """获取题目校对提示词。agent_prompt.json 为唯一来源，缺失时 fail-fast（ADR-00XX）。"""
        agent_lines = self.config.get("agent_prompt_lines")
        if not agent_lines:
            raise ValueError(
                "缺少 agent_prompt.json 或 agent_prompt_lines 为空，无法校对——请修复配置后重新发起校对")
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return "\n".join(agent_lines) + "\n\n" + tool_instructions
        return "\n".join(agent_lines)

    def get_review_prompt(self):
        """获取批注评审提示词。"""
        agent_lines = self.config.get("agent_prompt_lines")
        if not agent_lines:
            raise ValueError(
                "缺少 agent_prompt.json 或 agent_prompt_lines 为空，无法校对——请修复配置后重新发起校对")
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return "\n".join(agent_lines) + "\n\n" + tool_instructions
        return "\n".join(agent_lines)

    def split_lecture(self, md_file, output_root, base_name, options):
        if options is None:
            options = {}
        do_clean = options.get("do_clean", True)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)




