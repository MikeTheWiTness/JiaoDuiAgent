"""学科应用基类 —— 提供所有学科共用的零差异方法和默认实现。

子类只需覆盖必须学科化的方法（build_tools / get_tool_instructions /
get_max_tool_loops / prompt 方法 / split 方法 / proofread_one），
零差异方法自动继承。
"""
from core.config_loader import load_config
from core.defaults import (
    default_generate_knowledge,
    default_collect_paper_dirs,
)


class BaseSubjectApp:
    """学科应用基类。"""

    # ---- 子类必须覆盖的类属性 ----
    LEVEL: str = ""
    SUBJECT: str = ""
    name: str = ""
    version: str = "v3.0"

    # ---- 子类可覆盖的类属性 ----
    _show_knowledge_option: bool = True

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

    def get_knowledge_prompt(self):
        raise NotImplementedError

    def get_review_prompt(self):
        raise NotImplementedError

    def split_lecture(self, md_file, output_root, base_name, options):
        raise NotImplementedError

    def split_exam(self, md_file, output_root, base_name, options=None):
        raise NotImplementedError

    def proofread_one(self, api_url, api_key, model, q_dir, q_name,
                      is_knowledge, generate_pdf, source_mode="试卷"):
        raise NotImplementedError

    # ---- 零差异方法（7 科完全一致） ----

    def generate_knowledge(self, md_file, output_root, base_name):
        """知识提取 —— 所有学科完全相同。"""
        return default_generate_knowledge(md_file, output_root, base_name, self.config)

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
