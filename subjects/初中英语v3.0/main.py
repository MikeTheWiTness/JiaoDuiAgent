import importlib.util
import os
import shutil
import sys


def _get_resource_path(relative_path):
    """获取内置资源路径（_internal 内）。"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def _get_subject_dir():
    """获取学科目录（存放 config.json 和 .env 的目录）。

    - 打包后：exe 同级目录（用户可编辑 config.json）
    - 开发时：学科模块所在目录
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _ensure_config(subject_dir):
    """首次运行从内置资源复制 config.json 到 subject_dir。"""
    config_path = os.path.join(subject_dir, "config.json")
    if os.path.exists(config_path):
        return
    builtin_config = _get_resource_path("config.json")
    if os.path.exists(builtin_config):
        shutil.copy2(builtin_config, config_path)


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import tkinter as tk


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {name} ({path})")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    subject_dir = _get_subject_dir()
    _ensure_config(subject_dir)

    subject_mod = _load_module("subject", _get_resource_path("subject.py"))
    app_mod = _load_module("app", _get_resource_path("app.py"))
    subject_app = subject_mod.SubjectApp(subject_dir)
    root = tk.Tk()
    app_mod.SubjectGui(root, subject_app)
    root.mainloop()
