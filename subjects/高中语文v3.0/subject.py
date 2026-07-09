"""高中语文业务逻辑 —— 工具、提示词、拆分、校对、钩子。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 联网搜索工具已禁用，仅保留 pre_proofread_hook 中的预搜索阶段
# from shared.web_tools import WebSearchTool, WebFetchTool
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
from core.base_subject import BaseSubjectApp
import shutil
import re
from pathlib import Path
from shared.image_utils import copy_md_images


class SubjectApp(BaseSubjectApp):
    LEVEL = "高中"
    SUBJECT = "语文"
    name = "高中语文"
    version = "v3.0"

    def __init__(self, subject_dir):
        super().__init__(subject_dir)
        self._react_mode = False

    def build_tools(self):
        from shared.web_tools import WebFetchTool
        base = [WebFetchTool()]  # web_fetch 始终可用（前置检索 + 兜底）
        if self.react_mode:
            from shared.plan_tools import PlanUpdateTool
            from shared.text_nav_tools import LocateParagraphTool, ReadSectionTool
            base.append(PlanUpdateTool(nudge_template=""))
            base.append(LocateParagraphTool())
            base.append(ReadSectionTool())
        return base

    def get_max_tool_loops(self):
        return 15 if self.react_mode else 3

    # 可靠原文检索源（通过 web_fetch 直接构造 URL，无需经过搜索引擎）
    _DIRECT_SOURCES = [
        ("识典古籍", "https://www.shidianguji.com/search/{kw}",
         "文言文原文检索，直接返回古籍全文"),
        ("搜韵网", "https://sou-yun.cn/QueryPoem.aspx?q={kw}",
         "古诗词检索，返回诗词全文"),
        ("中国作家网", "https://www.chinawriter.com.cn/search?q={kw}",
         "现代散文/小说原文，收录《光明日报》《人民文学》等副刊文章"),
        ("百度直达", "https://www.baidu.com/s?wd={kw}",
         "通用原文查找，用 site: 前缀限定站点，如 wd=site:chinawriter.com.cn 叶梅 根河之恋"),
    ]

    def get_tool_instructions(self):
        web_tools = [t for t in self.tools if t.name == "web_search" or t.name == "web_fetch"]

        lines = []
        # 构建可靠来源列表（始终输出工具指令，无论工具是否已实例化）
        sources = "\n".join(
            f"  - **{name}**: `web_fetch(url=\"{url.format(kw='关键词')}\")` — {desc}"
            for name, url, desc in self._DIRECT_SOURCES
        )

        lines.append(
            "\n## 原文检索（仅供极端情况使用）\n"
            "**你是一位资深语文教研员，你的核心能力是基于自身知识直接校对，不是搜索。**\n"
            "\n"
            "仅在以下情况才可检索原文，且必须用 **web_fetch 直达以下网站**，"
            "严禁使用 web_search（搜索引擎对你不可用）。\n"
            "\n"
            f"{sources}\n"
            "\n"
            "**使用规则**：\n"
            "- 文言文无前置参考 → 识典古籍 一次（原文中摘几句作关键词）\n"
            "- 古诗词无前置参考 → 搜韵网 一次\n"
            "- 现代文需核对原文引用 → 中国作家网 或 百度直达（加 site: 限定）一次\n"
            "- 任一网站无结果 → **立即用自身知识判断，不得换网站再试，不得换关键词重搜**\n"
            "\n"
            "**严禁搜索的情形**：\n"
                "- 错别字、标点错误、病句 → 你自身完全能判断\n"
                "- 现代文阅读、诗歌鉴赏 → 原文引用正确性你可以凭训练数据判断\n"
                "- 答案选项对错分析 → 不需搜索\n"
                "- 有「前置参考」时 → 严禁一切检索\n"
                "- 任何情况下不得为了「确认一下」而搜索\n"
            )

        return "".join(lines)

    def get_question_prompt(self):
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
        if self.react_mode:
            # ReAct 统一入口：agent_prompt 已含知识维度叠加 + 题目节点图
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                base_prompt = "\n".join(agent_lines)
                tool_instructions = self.get_tool_instructions()
                if tool_instructions:
                    return base_prompt + "\n\n" + tool_instructions
                return base_prompt
        # 非 ReAct 模式：使用旧版 knowledge_prompt_lines
        base_prompt = "\n".join(self.config.get("knowledge_prompt_lines", []))
        tool_instructions = self.get_tool_instructions()
        if tool_instructions:
            return base_prompt + "\n\n" + tool_instructions
        return base_prompt

    def split_lecture(self, md_file, output_root, base_name, options):
        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")
        do_clean = options.get("do_clean", True)

        if split_mode == "rule":
            from shared.decor_utils import strip_decor_images_from_file
            strip_decor_images_from_file(md_file)
            return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # 预清洗：去除装饰图片（对齐高中历史）
        from shared.decor_utils import strip_decor_images
        md_content = strip_decor_images(md_content)

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
            return default_split_lecture(md_file, output_root, base_name, do_clean, self.config)

        return self._write_problems_to_dirs(md_file, output_root, base_name, problems)


    def get_review_prompt(self):
        from shared.review_mode import build_review_prompt
        if self.react_mode:
            agent_lines = self.config.get("agent_prompt_lines")
            if agent_lines:
                base_prompt = "\n".join(agent_lines)
                # ReAct 代理模式：agent_prompt 已含完整校对流程，
                # build_review_prompt 的无批注 else 分支是冗余指令，
                # 会与 agent_prompt 冲突（"用工具" vs "直接输出"）。
                # 仅在有批注时才追加评审指令。
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

    def _build_pre_hook(self, api_url, api_key, model, q_dir):
        """构建前置校对钩子：文言文/诗歌的前置搜索 + 自动 diff。"""
        def pre_hook(md_content):
            return self.pre_proofread_hook(md_content, api_url, api_key, model, q_dir=q_dir)
        return pre_hook


    def pre_proofread_hook(self, md_text, api_url=None, api_key=None, model=None, q_dir=None):
        from shared.chinese_classics_tools import preprocess_for_proofread
        return preprocess_for_proofread(md_text, api_url, api_key, model, q_dir=q_dir)

