"""小学数学业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.sympy_tools.tools import (
    EvaluateExpressionTool,
    SolveEquationTool,
    CheckEqualityTool,
    SimplifyExpressionTool,
)
from core.config_loader import load_config
from core.defaults import (
    default_split_lecture,
    default_split_exam,
    default_generate_knowledge,
    default_proofread_one,
    default_collect_paper_dirs,
)

LEVEL = "小学"
SUBJECT = "数学"


class SubjectApp:
    LEVEL = "小学"
    SUBJECT = "数学"
    name = "小学数学"
    version = "v1.1"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.tools = self.build_tools()

    def build_tools(self):
        """构建小学数学专用工具集。"""
        return [
            EvaluateExpressionTool(),
            SolveEquationTool(),
            CheckEqualityTool(),
            SimplifyExpressionTool(),
        ]

    def get_max_tool_loops(self):
        """工具调用最大循环次数。小学数学较简单，使用较小值。"""
        return 10

    def get_tool_instructions(self):
        """生成工具使用指令。"""
        sympy_tools = [t for t in self.tools if t.name in (
            "evaluate_expression", "solve_equation", "check_equality", "simplify_expression"
        )]
        if not sympy_tools:
            return ""
        lines = ["## 可用的符号计算工具",
                 "你在校对该学科题目时，可以使用以下工具进行**实算验证**，不得凭模型自身估算数值结果：",
                 ""]
        lines.extend(f"- `{t.name}`: {t.description}" for t in sympy_tools)
        lines.append("\n使用规则：对于需要数值计算、方程求解、公式推导验证的步骤，必须调用对应工具获取精确结果。")
        return "\n".join(lines)

    def get_question_prompt(self):
        """获取题目校对提示词。"""
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def get_knowledge_prompt(self):
        """获取知识提取提示词。"""
        base_prompt = "\n".join(self.config.get("knowledge_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def split_lecture(self, md_file, output_root, base_name, options=None):
        """讲义拆分 —— 复用默认实现。"""
        if options is None:
            options = {}
        do_clean = options.get("do_clean", True)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)

    def split_exam(self, md_file, output_root, base_name, options=None):
        """试卷拆分 —— 复用默认实现。"""
        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")
        if split_mode == "rule":
            return default_split_exam(md_file, output_root, base_name, self.config)
        from core.logging_utils import log
        log(f"⚠️ 未知分割模式: {split_mode}，使用规则模式")
        return default_split_exam(md_file, output_root, base_name, self.config)

    def generate_knowledge(self, md_file, output_root, base_name):
        """知识提取 —— 复用默认实现。"""
        return default_generate_knowledge(md_file, output_root, base_name, self.config)

    def proofread_one(self, api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf, source_mode="试卷"):
        """单题校对 —— 复用默认实现。"""
        if is_knowledge:
            prompt = self.get_knowledge_prompt()
        else:
            prompt = self.get_question_prompt()
        return default_proofread_one(
            api_url, api_key, model, q_dir, q_name, is_knowledge,
            prompt, self.tools, self.get_max_tool_loops(), generate_pdf
        )

    def collect_paper_dirs(self, base_path):
        """收集试卷目录 —— 复用默认实现。"""
        return default_collect_paper_dirs(base_path)

    def pre_proofread_hook(self, md_text):
        """校对前钩子 —— 空实现。"""
        return md_text

    def post_proofread_hook(self, result, q_dir):
        """校对后钩子 —— 空实现。"""
        return result

    def get_ui_features(self):
        """获取 UI 功能开关。"""
        return {
            "show_clean_table_option": True,
            "show_knowledge_option": True,
            "show_pdf_option": True,
            "show_parallel_option": True,
            "show_source_modes": ["讲义", "试卷"],
            "show_exec_modes": ["完整流程", "仅转换", "仅拆分", "仅校对", "仅生成PDF"],
            "show_split_mode_option": True,
            "add_file_title": "添加文件",
            "add_folder_title": "添加文件夹",
        }