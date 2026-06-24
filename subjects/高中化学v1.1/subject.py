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
from core.config_loader import load_config
from core.defaults import (
    default_split_lecture,
    default_split_exam,
    default_generate_knowledge,
    default_proofread_one,
    default_collect_paper_dirs,
)

LEVEL = "高中"
SUBJECT = "化学"


class SubjectApp:
    name = "高中化学"
    version = "v1.1"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self):
        """构建高中化学专用工具集。"""
        return [
            EvaluateExpressionTool(),
            SolveEquationTool(),
            CheckEqualityTool(),
            SimplifyExpressionTool(),
            BalanceChemicalEquationTool(),
            StoichiometryCalcTool(),
        ]

    def get_max_tool_loops(self):
        """工具调用最大循环次数。"""
        return 15

    def get_tool_instructions(self, tools):
        """生成工具使用指令。"""
        instructions = []
        for tool in tools:
            if tool.name == "evaluate_expression":
                instructions.append(
                    "evaluate_expression: 求值数学表达式，支持四则运算、幂运算、科学计数法等。"
                    "用于化学计算题答案验证时，必须用此工具实算，不得凭模型自身估算。"
                )
            elif tool.name == "solve_equation":
                instructions.append(
                    "solve_equation: 求解一元或多元方程。适用于化学平衡计算、pH计算等。"
                )
            elif tool.name == "balance_chemical_equation":
                instructions.append(
                    "balance_chemical_equation: 配平化学方程式。输入格式：反应物 -> 产物，"
                    "如 'Fe + O2 -> Fe2O3'。配平类题目必须用此工具验证配平结果。"
                )
            elif tool.name == "stoichiometry_calc":
                instructions.append(
                    "stoichiometry_calc: 根据配平方程式进行化学计量计算（质量→质量）。"
                    "计算题必须用此工具实算验证。"
                )
            elif tool.name == "check_equality":
                instructions.append(
                    "check_equality: 检查两个表达式是否等价。适用于验证公式变形。"
                )
            elif tool.name == "simplify_expression":
                instructions.append(
                    "simplify_expression: 化简数学表达式。可用于表达式化简。"
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