"""初中英语 GUI —— 继承默认模板。"""
import sys
sys.path.insert(0, sys.path[0].replace(r'subjects\\初中英语', ''))

from ui.default_app import DefaultApp


class SubjectGui(DefaultApp):
    """初中英语 GUI：与默认模板基本一致，仅改标题。"""
    
    def __init__(self, root, subject_app):
        super().__init__(root, subject_app)
