"""高中物理业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""

from core.base_subject import BaseSubjectApp
from core.defaults import (
    default_split_lecture,
)
from shared.sympy_tools.tools import (
    CircleFromTwoPointsTool,
    DimensionalAnalysisTool,
    EvaluateExpressionTool,
    SolveEquationTool,
    SolvePhysicsFormulaTool,
    VectorOperationsTool,
)
class SubjectApp(BaseSubjectApp):
    LEVEL = "高中"
    SUBJECT = "物理"
    name = "高中物理"
    version = "v3.0"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)

    def build_tools(self):
        base = [
            EvaluateExpressionTool(),
            SolveEquationTool(),
            SolvePhysicsFormulaTool(),
            DimensionalAnalysisTool(),
            VectorOperationsTool(),
            CircleFromTwoPointsTool(),
        ]
        from shared.physics_tools import IndependentSolveTool
        from shared.plan_tools import PlanUpdateTool
        # 物理 nudge 置空：自检靠 prompt 第 8 步，不依赖工具 nudge（ADR-0006 决策 2）
        base.append(PlanUpdateTool(nudge_template=""))
        base.append(IndependentSolveTool())
        return base

    def get_max_tool_loops(self):
        return 30

    def get_tool_instructions(self):
        sympy_tools = [t for t in self.tools if t.name not in ("web_search", "web_fetch",
                         "plan_update", "independent_solve")]
        web_tools = [t for t in self.tools if t.name == "web_search" or t.name == "web_fetch"]

        lines = []

        if sympy_tools:
            lines.append("## 可用的符号计算工具\n"
                "你在校对该学科题目时，可以使用以下工具进行**实算验证**，不得凭模型自身估算数值结果：\n")
            lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in sympy_tools))
            lines.append("\n使用规则：对于需要数值计算、方程求解、公式推导验证的步骤，必须调用对应工具获取精确结果。\n")

        if web_tools:
            lines.append("## 可用的联网搜索工具\n"
                "如需查找最新说法、验证专业术语、检索不在训练数据内的信息，可使用：\n")
            lines.append("\n".join(f"- `{t.name}`: {t.description}" for t in web_tools))
            lines.append("\n使用规则：先调 web_search 搜索，若需查看详情页再调 web_fetch 抓取。"
                "搜索失败或超时是正常情况，此时使用模型自身知识继续。\n")

        return "".join(lines)

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
        do_clean = options.get("do_clean", True)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)




