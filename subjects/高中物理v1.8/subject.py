import os

from shared.sympy_tools.tools import (
    EvaluateExpressionTool,
    SolveEquationTool,
    SolvePhysicsFormulaTool,
    DimensionalAnalysisTool,
    VectorOperationsTool,
    CircleFromTwoPointsTool,
)
from shared.web_tools import WebSearchTool
from core.config_loader import load_config
from core.defaults import (
    default_split_lecture,
    default_split_exam,
    default_generate_knowledge,
    default_proofread_one,
    default_collect_paper_dirs,
)


class SubjectApp:
    LEVEL = "高中"
    SUBJECT = "物理"
    name = "高中物理"
    version = "v1.8"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self):
        return [
            EvaluateExpressionTool(),
            SolveEquationTool(),
            SolvePhysicsFormulaTool(),
            DimensionalAnalysisTool(),
            VectorOperationsTool(),
            CircleFromTwoPointsTool(),
            WebSearchTool(),
        ]

    def get_max_tool_loops(self):
        return 20

    def get_tool_instructions(self):
        sympy_tools = [t for t in self.tools if t.name != "web_search" and t.name != "web_fetch"]
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
        prompt_lines = self.config.get("question_prompt_lines", [])
        base_prompt = "\n".join(prompt_lines)
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def get_knowledge_prompt(self):
        prompt_lines = self.config.get("knowledge_prompt_lines", [])
        base_prompt = "\n".join(prompt_lines)
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def split_lecture(self, md_file, output_root, base_name, options):
        do_clean = options.get("do_clean", True)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)

    def split_exam(self, md_file, output_root, base_name):
        return default_split_exam(md_file, output_root, base_name, self.config)

    def generate_knowledge(self, md_file, output_root, base_name):
        return default_generate_knowledge(md_file, output_root, base_name, self.config)

    def proofread_one(self, api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf):
        if is_knowledge:
            prompt = self.get_knowledge_prompt()
        else:
            prompt = self.get_question_prompt()
        return default_proofread_one(
            api_url, api_key, model, q_dir, q_name, is_knowledge,
            prompt, self.tools, self.get_max_tool_loops(), generate_pdf
        )

    def collect_paper_dirs(self, base_path):
        return default_collect_paper_dirs(base_path)

    def pre_proofread_hook(self, md_text):
        return md_text

    def post_proofread_hook(self, result, q_dir):
        return result
