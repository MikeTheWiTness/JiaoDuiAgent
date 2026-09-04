"""高中历史业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.base_subject import BaseSubjectApp
from core.defaults import (
    default_split_lecture,
)
from core.logging_utils import log
from core.manual_split import split_by_unit_markers


class SubjectApp(BaseSubjectApp):
    LEVEL = "高中"
    SUBJECT = "历史"
    name = "高中历史"
    version = "v3.0"
    _show_knowledge_option = False
    _clean_bold_replacement = r"\1"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)

    def build_tools(self):
        from shared.plan_tools import PlanUpdateTool
        return [PlanUpdateTool(nudge_template="")]

    def get_max_tool_loops(self):
        return 15

    def get_tool_instructions(self):
        # 历史学科不需要联网检索工具（史实主要靠 LLM 自身知识），仅提供 plan_update
        return ""

    def get_question_prompt(self):
        agent_lines = self.config.get("agent_prompt_lines")
        if not agent_lines:
            raise ValueError(
                "缺少 agent_prompt.json 或 agent_prompt_lines 为空，无法校对——请修复配置后重新发起校对")
        return "\n".join(agent_lines)

    def split_lecture(self, md_file, output_root, base_name, options):
        from shared.decor_utils import strip_decor_images
        from shared.split_post_utils import mark_navigation_units

        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")
        do_clean = options.get("do_clean", True)

        if split_mode == "rule":
            # 预清洗：去除装饰图片
            result = default_split_lecture(md_file, output_root, base_name, do_clean, self.config)
            # 后处理：删除导航/封面板块
            if result:
                mark_navigation_units(output_root, base_name)
            return result

        with open(md_file, encoding='utf-8') as f:
            md_content = f.read()

        # 预清洗：去除装饰图片
        md_content = strip_decor_images(md_content)

        if split_mode == "none":
            problems = [{"content": md_content}]
        elif split_mode == "manual":
            problems = split_by_unit_markers(md_content)
        elif split_mode == "smart":
            api_url = options.get("api_url", "")
            api_key = options.get("api_key", "")
            model = options.get("model", "")
            api_format = options.get("api_format", "chat/completions")
            from shared.smart_split import smart_split
            problems = smart_split(md_content, api_url, api_key, model,
                               md_file=md_file, output_root=output_root,
                               api_format=api_format)
        else:
            log(f"⚠️ 未知分割模式: {split_mode}，使用规则模式")
            return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)

        return self._write_problems_to_dirs(md_file, output_root, base_name, problems)


    def get_review_prompt(self):
        agent_lines = self.config.get("agent_prompt_lines")
        if not agent_lines:
            raise ValueError(
                "缺少 agent_prompt.json 或 agent_prompt_lines 为空，无法校对——请修复配置后重新发起校对")
        return "\n".join(agent_lines)




