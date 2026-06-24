import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox


class LogPanel:
    def __init__(self, parent):
        self.log_text = scrolledtext.ScrolledText(parent, height=12, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

    def append(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.update_idletasks()


class ApiDialog:
    def __init__(self, parent, api_config, on_save):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("API 配置")
        self.dialog.geometry("480x220")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.on_save = on_save

        frame = ttk.Frame(self.dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="接口地址：").grid(row=0, column=0, sticky=tk.W, pady=6)
        self.e_url = ttk.Entry(frame, width=50)
        self.e_url.grid(row=0, column=1, padx=6, pady=6)
        self.e_url.insert(0, api_config.get("api_url", ""))

        ttk.Label(frame, text="API 密钥：").grid(row=1, column=0, sticky=tk.W, pady=6)
        self.e_key = ttk.Entry(frame, width=50, show="*")
        self.e_key.grid(row=1, column=1, padx=6, pady=6)
        self.e_key.insert(0, api_config.get("api_key", ""))

        ttk.Label(frame, text="模型名称：").grid(row=2, column=0, sticky=tk.W, pady=6)
        self.e_model = ttk.Entry(frame, width=50)
        self.e_model.grid(row=2, column=1, padx=6, pady=6)
        self.e_model.insert(0, api_config.get("model_name", ""))

        ttk.Button(frame, text="保存", command=self._do_save).grid(row=3, column=0, columnspan=2, pady=12)

    def _do_save(self):
        url = self.e_url.get().strip()
        key = self.e_key.get().strip()
        model = self.e_model.get().strip()
        if not url or not key or not model:
            return
        self.on_save(url, key, model)
        self.dialog.destroy()


class ModeSelector:
    def __init__(self, parent, source_var, exec_var, on_change):
        self.source_var = source_var
        self.exec_var = exec_var
        self.on_change = on_change
        self.parent = parent

        self.frame_source = ttk.Frame(parent, padding=10)
        self.frame_source.pack(fill=tk.X)
        self.source_label = ttk.Label(self.frame_source, text="来源模式：")
        self.source_label.pack(side=tk.LEFT)
        self.source_buttons = []

        self.f1 = ttk.Frame(parent, padding=10)
        self.f1.pack(fill=tk.X)
        ttk.Label(self.f1, text="执行模式：").pack(side=tk.LEFT)
        self.exec_buttons = []

        self._source_options = ["讲义", "试卷"]
        self._exec_options = ["完整流程", "仅转换", "仅拆分", "仅校对", "仅生成PDF"]

        self._build_source_buttons()
        self._build_exec_buttons()

    def _build_source_buttons(self):
        for btn in self.source_buttons:
            btn.destroy()
        self.source_buttons = []
        for opt in self._source_options:
            btn = ttk.Radiobutton(self.frame_source, text=f"{opt}模式",
                                  variable=self.source_var, value=opt,
                                  command=self._on_change)
            btn.pack(side=tk.LEFT, padx=4)
            self.source_buttons.append(btn)

    def _build_exec_buttons(self):
        for btn in self.exec_buttons:
            btn.destroy()
        self.exec_buttons = []
        for opt in self._exec_options:
            btn = ttk.Radiobutton(self.f1, text=opt,
                                  variable=self.exec_var, value=opt,
                                  command=self._on_change)
            btn.pack(side=tk.LEFT, padx=4)
            self.exec_buttons.append(btn)

    def set_source_options(self, options):
        if not options:
            return
        self._source_options = list(options)
        if self.source_var.get() not in options:
            self.source_var.set(options[0])
        self._build_source_buttons()

    def set_exec_options(self, options):
        if not options:
            return
        self._exec_options = list(options)
        if self.exec_var.get() not in options:
            self.exec_var.set(options[0])
        self._build_exec_buttons()

    def _on_change(self):
        if self.on_change:
            self.on_change()

    def pack_forget_source(self):
        self.frame_source.pack_forget()

    def pack_source(self, before=None):
        if before:
            self.frame_source.pack(fill=tk.X, before=before)
        else:
            self.frame_source.pack(fill=tk.X)
