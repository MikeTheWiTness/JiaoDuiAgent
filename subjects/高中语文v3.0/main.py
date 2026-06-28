import sys, os, importlib.util
from typing import Any

def _get_resource_path(relative_path: str) -> str:
    try:
        base_path: str = getattr(sys, "_MEIPASS")
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import tkinter as tk

_here = _get_resource_path("")

def _load_module(name: str, path: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {name} ({path})")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

if __name__ == "__main__":
    subject_mod = _load_module("subject", _get_resource_path("subject.py"))
    app_mod = _load_module("app", _get_resource_path("app.py"))
    subject_app = subject_mod.SubjectApp(_here)
    root = tk.Tk()
    app_mod.SubjectGui(root, subject_app)
    root.mainloop()