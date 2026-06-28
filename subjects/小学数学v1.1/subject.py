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
from core.manual_split import split_by_manual_markers
from core.logging_utils import log
import shutil
import re
from pathlib import Path


class SubjectApp:
    LEVEL = "小学"
    SUBJECT = "数学"
    name = "小学数学"
    version = "v3.0"

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self.react_mode = False
        self.tools = self.build_tools()

    def build_tools(self):
        """构建小学数学专用工具集。"""
        base = [
            EvaluateExpressionTool(),
            SolveEquationTool(),
            CheckEqualityTool(),
            SimplifyExpressionTool(),
        ]
        if self.react_mode:
            from shared.plan_tools import PlanUpdateTool
            from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool
            base.append(PlanUpdateTool())
            base.append(LocateParagraphTool())
            base.append(ReadSectionTool())
        return base

    def get_max_tool_loops(self):
        """工具调用最大循环次数。"""
        return 15 if self.react_mode else 10

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
        """获取题目校对提示词。ReAct 模式时优先用 agent_prompt。"""
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
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def get_knowledge_prompt(self):
        """获取知识提取提示词。ReAct 模式时优先用 agent_prompt。"""
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                base_prompt = "\n".join(agent_lines)
                tool_instructions = self.get_tool_instructions()
                if tool_instructions:
                    return base_prompt + "\n\n" + tool_instructions
                return base_prompt
        base_prompt = "\n".join(self.config.get("knowledge_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

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

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        if split_mode == "none":
            problems = [{"content": md_content}]
        elif split_mode == "manual":
            problems = split_by_manual_markers(md_content)
        elif split_mode == "smart":
            api_url = options.get("api_url", "")
            api_key = options.get("api_key", "")
            model = options.get("model", "")
            from shared.smart_split import smart_split
            problems = smart_split(md_content, api_url, api_key, model, md_file=md_file)
        else:
            log(f"⚠️ 未知分割模式: {split_mode}，使用规则模式")
            return default_split_exam(md_file, output_root, base_name, self.config)

        return self._write_problems_to_dirs(md_file, output_root, base_name, problems)

    def _write_problems_to_dirs(self, md_file, output_root, base_name, problems):
        if not problems:
            log("⚠️ 没有题目可写入")
            return False

        md_dir = Path(md_file).parent
        src_media = md_dir / f"{base_name}_images" / "media"
        target_root = Path(output_root) / base_name
        target_root.mkdir(parents=True, exist_ok=True)

        for idx, prob in enumerate(problems, start=1):
            content = prob.get("content", "")
            q_dir = target_root / f"第{idx}题"
            q_dir.mkdir(exist_ok=True)
            img_dir = q_dir / "images"
            img_dir.mkdir(exist_ok=True)

            img_pat = re.compile(r'!\[(.*?)\]\((.*?)\)')
            def _copy_img(m):
                alt, src = m.group(1), m.group(2).strip()
                if src.startswith('http://') or src.startswith('https://'):
                    return m.group(0)
                img_name = Path(src).name
                src_path = None
                candidates = [
                    src_media / img_name,
                    md_dir / src,
                    md_dir / Path(src).name,
                ]
                for cand in candidates:
                    try:
                        if cand.exists() and cand.is_file():
                            src_path = cand
                            break
                    except Exception:
                        pass
                if src_path:
                    dest = img_dir / img_name
                    if not dest.exists():
                        try:
                            shutil.copy2(src_path, dest)
                        except Exception:
                            pass
                    return f"![{alt}](./images/{img_name})"
                return m.group(0)
            new_content = img_pat.sub(_copy_img, content)

            (q_dir / f"第{idx}题.md").write_text(new_content, encoding='utf-8')

            # 同步生成 _clean.md
            try:
                from shared.docx_format_enhancer import strip_format_markers
                clean = strip_format_markers(new_content)
                clean = re.sub(r'<批注\s+id=\d+>.*?</批注>', '', clean, flags=re.DOTALL)
                clean = re.sub(r'\*\*([^*]+)\*\*', r'', clean)
                clean = re.sub(r'__([^_]+)__', r'', clean)
                (q_dir / f"第{idx}题_clean.md").write_text(clean, encoding='utf-8')
            except Exception:
                pass

        log(f"📂 拆分完成: {len(problems)} 题")
        return True

    def generate_knowledge(self, md_file, output_root, base_name):
        """知识提取 —— 复用默认实现。"""
        return default_generate_knowledge(md_file, output_root, base_name, self.config)

    def proofread_one(self, api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf, source_mode="试卷"):
        """单题校对 —— 复用默认实现。"""
        if is_knowledge:
            prompt = self.get_knowledge_prompt()
        elif source_mode == "批注评审":
            prompt = self.get_review_prompt()
        else:
            prompt = self.get_question_prompt()

        return default_proofread_one(
            api_url, api_key, model, q_dir, q_name, is_knowledge,
            prompt, self.tools, self.get_max_tool_loops(), generate_pdf,
            react_mode=self.react_mode
        )

    def collect_paper_dirs(self, base_path):
        """收集试卷目录 —— 复用默认实现。"""
        return default_collect_paper_dirs(base_path)

    def get_ui_features(self):
        """获取 UI 功能开关。"""
        return {
            "show_clean_table_option": True,
            "show_knowledge_option": True,
            "show_pdf_option": True,
            "show_parallel_option": True,
            "show_source_modes": ["讲义", "试卷", "自由校对", "批注评审"],
            "show_exec_modes": ["完整流程", "仅转换", "仅拆分", "仅校对", "仅生成PDF"],
            "show_split_mode_option": True,
            "add_file_title": "添加文件",
            "add_folder_title": "添加文件夹",
        }

    def pre_proofread_hook(self, md_text, api_url=None, api_key=None, model=None, q_dir=None):
        """校对前钩子 —— 空实现。"""
        return md_text

    def post_proofread_hook(self, result, q_dir):
        """校对后钩子 —— 空实现。"""
        return result
