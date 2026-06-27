# ReAct mode additions for DefaultApp.
# Add these to the existing DefaultApp class manually or merge.
# 1. In __init__, add after self.parallel_count setup:
#    self.react_enabled = tk.BooleanVar(value=True)
# 2. In setup_ui, add checkbox in frame_pdf_options:
#    ttk.Checkbutton(self.frame_pdf_options, text="ReAct 模式",
#                    variable=self.react_enabled,
#                    command=self._on_react_toggled).pack(side=tk.LEFT, padx=4)
# 3. Add method:
#    def _on_react_toggled(self):
#        self.subject_app.react_mode = self.react_enabled.get()
#        log(f"ReAct 模式: {'ON' if self.react_enabled.get() else 'OFF'}")
