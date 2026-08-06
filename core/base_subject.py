"""学科应用基类 —— 提供所有学科共用的零差异方法和默认实现。

子类只需覆盖必须学科化的方法（build_tools / get_tool_instructions /
get_max_tool_loops / prompt 方法 / split 方法 / proofread_one），
零差异方法自动继承。
"""
import re
from pathlib import Path

from core.config_loader import load_config
from core.defaults import (
    default_collect_paper_dirs,
    default_proofread_one,
    default_split_exam,
)
from core.logging_utils import log
from core.manual_split import split_by_unit_markers
from shared.image_utils import copy_md_images


class BaseSubjectApp:
    """学科应用基类。"""

    # ---- 子类必须覆盖的类属性 ----
    LEVEL: str = ""
    SUBJECT: str = ""
    name: str = ""
    version: str = "v3.0"

    # ---- 子类可覆盖的类属性 ----
    _show_knowledge_option: bool = False  # 统一模型下默认隐藏，历史等学科可覆盖为 True
    _clean_bold_replacement: str = "\x01"  # 高中历史覆盖为 "\1" 保留粗体文本

    def __init__(self, subject_dir):
        self.subject_dir = subject_dir
        self.config = load_config(subject_dir)
        self._react_mode = False
        self.tools = self.build_tools()

    # ---- react_mode 属性（统一的 property 模式） ----

    @property
    def react_mode(self):
        return self._react_mode

    @react_mode.setter
    def react_mode(self, value):
        self._react_mode = value
        self.tools = self.build_tools()

    # ---- 子类必须实现的方法 ----

    def build_tools(self):
        raise NotImplementedError

    def get_max_tool_loops(self):
        raise NotImplementedError

    def get_tool_instructions(self):
        raise NotImplementedError

    def get_question_prompt(self):
        raise NotImplementedError

    def get_review_prompt(self):
        raise NotImplementedError

    def split_lecture(self, md_file, output_root, base_name, options):
        raise NotImplementedError

    def split_exam(self, md_file, output_root, base_name, options=None):
        raise NotImplementedError

    # ---- 零差异方法（7 科完全一致） ----

    def generate_knowledge(self, md_file, output_root, base_name):
        """知识提取 —— 已废弃（ADR-0017 决策3）。

        section 模式下知识标题被识别为板块边界，知识自然成为独立单元，
        不再需要单独提取到 知识/ 文件夹。保留函数体向后兼容。
        """
        import logging
        _log = logging.getLogger(__name__)
        _log.warning("generate_knowledge 已废弃（ADR-0017），section 模式下跳过")
        # 不再调用 default_generate_knowledge
        return False

    def collect_paper_dirs(self, base_path):
        """收集试卷目录 —— 所有学科完全相同。"""
        return default_collect_paper_dirs(base_path)

    def pre_proofread_hook(self, md_text, api_url=None, api_key=None, model=None, q_dir=None):
        """前置校对钩子 —— 默认透传。高中语文覆盖此方法注入文言文搜索。"""
        return md_text

    def post_proofread_hook(self, result, q_dir):
        """后置校对钩子 —— 默认透传。"""
        return result

    # ---- 高度相似方法（可通过类属性差异化） ----

    def get_ui_features(self):
        """UI 功能开关 —— 仅 show_knowledge_option 因学科而异（历史关闭）。"""
        return {
            "show_clean_table_option": True,
            "show_knowledge_option": self._show_knowledge_option,
            "show_pdf_option": True,
            "show_parallel_option": True,
            "show_source_modes": ["讲义", "试卷", "自由校对", "批注评审"],
            "show_exec_modes": ["完整流程", "仅转换", "仅拆分", "仅校对", "仅生成PDF"],
            "show_split_mode_option": True,
            "add_file_title": "添加文件",
            "add_folder_title": "添加文件夹",
        }

    def get_supported_file_types(self):
        """支持的文件类型 —— 默认实现。需定制（如小学语文加 .idml）的学科覆盖即可。"""
        return [
            ("支持的文件", "*.docx;*.doc;*.md;*.zip"),
            ("Word 文档", "*.docx;*.doc"),
            ("Markdown 文件", "*.md"),
            ("ZIP 压缩包", "*.zip"),
            ("所有文件", "*.*"),
        ]

    def get_supported_extensions(self):
        """支持的文件扩展名 —— 默认实现。"""
        return {".docx", ".doc", ".md"}

    # ---- proofread_one（模板方法，语文覆盖 _build_pre_hook） ----

    def proofread_one(self, ctx, q_dir, q_name,
                      generate_pdf, source_mode="试卷", archive_root=None):
        """校对入口 —— 所有学科共用骨架。高中语文覆盖 _build_pre_hook 注入文言文搜索。

        ADR-0017 决策6：移除 is_knowledge 参数。
        ReAct 模式下 LLM 通过 agent_prompt 第0步自行判定内容类型，
        程序侧不再按目录名决定校对策略。
        """
        if source_mode == "批注评审":
            prompt = self.get_review_prompt()
        else:
            prompt = self.get_question_prompt()

        pre_hook = self._build_pre_hook(ctx.api_url, ctx.api_key, ctx.model, q_dir)

        return default_proofread_one(
            ctx, q_dir, q_name,
            prompt, self.tools, generate_pdf,
            pre_hook=pre_hook,
            react_mode=self.react_mode,
            archive_root=archive_root,
        )

    def _build_pre_hook(self, api_url, api_key, model, q_dir):
        """构建前置校对钩子。默认返回 None。高中语文覆盖此方法注入文言文搜索。"""
        return None

    # ---- split_exam（所有学科完全相同） ----

    def split_exam(self, md_file, output_root, base_name, options=None):
        """试卷拆分 —— 所有学科遵循相同的 rule/manual/smart/none 模式。"""
        if options is None:
            options = {}
        split_mode = options.get("split_mode", "rule")

        if split_mode == "rule":
            return default_split_exam(md_file, output_root, base_name, self.config)

        with open(md_file, encoding='utf-8') as f:
            md_content = f.read()

        if split_mode == "none":
            problems = [{"content": md_content}]
        elif split_mode == "manual":
            problems = split_by_unit_markers(md_content)
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

    # ---- _write_problems_to_dirs（7 科最大重复源） ----

    def _write_problems_to_dirs(self, md_file, output_root, base_name, problems):
        """将拆分后的题目写入目录，含图片复制和 _clean.md 生成。"""
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

            img_result = copy_md_images(content, [src_media, md_dir], img_dir)
            new_content = img_result.content

            (q_dir / f"第{idx}题.md").write_text(new_content, encoding='utf-8')

            # 同步生成 _clean.md
            try:
                from shared.docx_format_enhancer import generate_clean_md
                clean = generate_clean_md(new_content, self._clean_bold_replacement)
                (q_dir / f"第{idx}题_clean.md").write_text(clean, encoding='utf-8')
            except Exception:
                pass

        log(f"📂 拆分完成: {len(problems)} 题")
        return True
