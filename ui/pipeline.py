"""管线阶段选择器 —— 4 个可独立开关的阶段。

替换原有的双层下拉（source_mode × exec_mode），改为直观的管线 toggle。
"""
import tkinter as tk
from tkinter import ttk


class PipelineBar(ttk.Frame):
    """管线阶段选择器。

    4 个阶段串行排列：导入 → 拆分 → 校对 → 排版。
    每个阶段可独立开启/关闭，阶段之间用箭头连接。

    开关组合自然决定工作流入口和出口：
    - ☑☑☑☑ 完整流程（Word → PDF）
    - ☑☑☐☐ 仅拆分
    - ☐☐☑☐ 仅校对（需预拆分目录）
    - ☐☐☐☑ 仅生成 PDF
    """

    STAGES = [
        ("import",  "导入", "📥"),
        ("split",   "拆分", "✂️"),
        ("proof",   "校对", "🔍"),
        ("typeset", "排版", "📄"),
    ]

    def __init__(self, parent, on_changed=None, **kw):
        super().__init__(parent, **kw)
        self.on_changed = on_changed
        self._vars: dict[str, tk.BooleanVar] = {}
        self._buttons: dict[str, ttk.Button] = {}

        self._build()

    def _build(self):
        """构建管线 UI：btn ── btn ── btn ── btn"""
        for i, (key, label, icon) in enumerate(self.STAGES):
            var = tk.BooleanVar(value=True)
            self._vars[key] = var

            btn = ttk.Button(
                self,
                text=f"{icon} {label}",
                command=lambda k=key: self._toggle(k),
            )
            btn.pack(side=tk.LEFT)
            self._buttons[key] = btn

            if i < len(self.STAGES) - 1:
                arrow = ttk.Label(self, text="──", font=("", 10))
                arrow.pack(side=tk.LEFT, padx=2)

        self._update_styles()

    def _toggle(self, key: str):
        """切换单个阶段，触发回调。"""
        var = self._vars[key]
        var.set(not var.get())
        self._update_styles()
        if self.on_changed:
            self.on_changed()

    def _update_styles(self):
        """根据开关状态更新按钮样式。"""
        for key, btn in self._buttons.items():
            active = self._vars[key].get()
            if active:
                btn.configure(style="Pipeline.Active.TButton")
            else:
                btn.configure(style="Pipeline.Inactive.TButton")

    # ---- 公共 API ----

    def is_active(self, key: str) -> bool:
        return self._vars[key].get()

    def set_active(self, key: str, value: bool):
        self._vars[key].set(value)
        self._update_styles()
        if self.on_changed:
            self.on_changed()

    @property
    def import_enabled(self) -> bool:
        return self.is_active("import")

    @property
    def split_enabled(self) -> bool:
        return self.is_active("split")

    @property
    def proof_enabled(self) -> bool:
        return self.is_active("proof")

    @property
    def typeset_enabled(self) -> bool:
        return self.is_active("typeset")

    def active_stages(self) -> list[str]:
        """返回当前激活的阶段 key 列表。"""
        return [k for k, v in self._vars.items() if v.get()]


def setup_pipeline_styles(style: ttk.Style):
    """注册管线组件的 ttk 样式（在 root 创建后调用一次）。"""
    style.configure(
        "Pipeline.Active.TButton",
        font=("", 10, "bold"),
        padding=(12, 6),
    )
    style.configure(
        "Pipeline.Inactive.TButton",
        font=("", 10, "overstrike"),
        padding=(12, 6),
        foreground="gray",
    )
