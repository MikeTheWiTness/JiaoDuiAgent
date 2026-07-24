import tkinter as tk
from tkinter import scrolledtext, ttk


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


