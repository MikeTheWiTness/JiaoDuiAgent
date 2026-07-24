"""小学数学 GUI —— 继承默认模板。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.default_app import DefaultApp


class SubjectGui(DefaultApp):
    """小学数学 GUI：与默认模板基本一致。"""

    def __init__(self, root, subject_app):
        super().__init__(root, subject_app)
