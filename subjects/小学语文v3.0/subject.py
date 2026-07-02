"""小学语文业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
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
    default_convert_file_to_md,
    get_supported_extensions,
)
from core.manual_split import split_by_manual_markers
from core.logging_utils import log
from core.base_subject import BaseSubjectApp
from shared.image_utils import copy_md_images
import shutil
import re
from pathlib import Path


class SubjectApp(BaseSubjectApp):
    LEVEL = "小学"
    SUBJECT = "语文"
    name = "小学语文"
    version = "v3.0"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)
        self._react_mode = False

    def build_tools(self):
        """构建小学语文专用工具集。语文以文字校对为主。"""
        base = []
        if self.react_mode:
            from shared.plan_tools import PlanUpdateTool
            from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool
            base.append(PlanUpdateTool())
            base.append(LocateParagraphTool())
            base.append(ReadSectionTool())
        return base

    def get_max_tool_loops(self):
        """工具调用最大循环次数。"""
        return 15 if self.react_mode else 0

    def get_tool_instructions(self):
        """生成工具使用指令。"""
        if not self.tools:
            return ""
        lines = []
        plan_tools = [t for t in self.tools if t.name in ("plan_update", "locate_paragraph", "read_section")]
        if plan_tools:
            lines.extend(f"- `{t.name}`: {t.description}" for t in plan_tools)
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
        return "\n".join(self.config.get("knowledge_prompt_lines", []))

    def get_review_prompt(self):
        """获取批注评审提示词。"""
        from shared.review_mode import build_review_prompt
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                return "\n".join(agent_lines)
        base_prompt = "\n".join(self.config.get("question_prompt_lines", []))
        return base_prompt + "\n\n" + build_review_prompt("")

    def get_supported_extensions(self):
        """返回支持的文件扩展名集合。"""
        exts = get_supported_extensions()
        exts.add(".md")
        exts.add(".idml")
        return exts

    def convert_file_to_md(self, file_path, output_md, img_dir, use_mathjax=False):
        """文件转 Markdown。支持 Word 和 IDML 格式。"""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".idml":
            try:
                from core.idml_extractor import extract_idml_to_markdown
                log("   📖 检测到 IDML 文件，使用 IDML 提取器...")
                result = extract_idml_to_markdown(file_path, output_md)
                log(f"   ✅ IDML 提取完成：{result['paragraph_count']} 段，"
                    f"涉及 {result['page_count']} 页")
                return {"success": True, "needs_post_process": False}
            except Exception as e:
                log(f"   ❌ IDML 提取失败: {e}")
                return {"success": False, "needs_post_process": False}

        return default_convert_file_to_md(file_path, output_md, img_dir, use_mathjax)

    def split_lecture(self, md_file, output_root, base_name, options):
        if options is None:
            options = {}
        do_clean = options.get("do_clean", True)
        from shared.decor_utils import strip_decor_images_from_file
        strip_decor_images_from_file(md_file)
        return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)




    def post_convert_hook(self, md_path, source="讲义"):
        """转换后钩子，在所有后处理完成后、拆分前调用。"""
        pass
