import os, re, json, base64, time, shutil, subprocess, threading, zipfile, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path

from core.env_config import load_env_config, save_env_config
from core.logging_utils import set_log_func, log
from core.pandoc_utils import check_pandoc, convert_with_pandoc
from core.defaults import (
    fix_latex_escapes, clean_md_file, fix_floating_images,
    normalize_option_spacing, post_process_md_zw
)
from shared.latex_generator import generate_combined_pdf
from ui.widgets import LogPanel, ApiDialog, ModeSelector


DEFAULT_OUTPUT = "output"
BATCH_SIZE = 10


class DefaultApp:
    def __init__(self, root, subject_app):
        self.root = root
        self.subject_app = subject_app
        version = getattr(subject_app, 'version', '')
        title = f"{subject_app.name}校对工具 {version}".strip()
        self.root.title(title)
        self.root.geometry("1050x750")
        self.root.minsize(900, 650)

        self.source_mode = tk.StringVar(value="讲义")
        self.exec_mode = tk.StringVar(value="完整流程")
        self.output_dir = tk.StringVar(value="output")

        self.clean_enabled = tk.BooleanVar(value=True)
        self.knowledge_enabled = tk.BooleanVar(value=True)

        self.generate_pdf = tk.BooleanVar(value=True)

        self.parallel_enabled = tk.BooleanVar(value=True)
        self.parallel_count = tk.StringVar(value="10")

        self.split_mode = tk.StringVar(value="rule")
        self.free_text = ""
        self.free_images = []

        self.file_list = []
        self.proofread_list = []
        self.proofread_result = {}
        self.task_running = False
        self.task_interrupt = False

        self.api_config = load_env_config(subject_app.subject_dir)

        self.system_prompt = subject_app.get_question_prompt()
        self.knowledge_prompt = subject_app.get_knowledge_prompt()
        self.tools = subject_app.tools

        self.setup_ui()
        self.update_ui_for_mode()

    def _get_ui_features(self):
        """获取学科自定义的 UI 功能开关。"""
        default_features = {
            "show_clean_table_option": True,
            "show_knowledge_option": True,
            "show_pdf_option": True,
            "show_parallel_option": True,
            "show_source_modes": ["讲义", "试卷"],
            "show_exec_modes": ["完整流程", "仅转换", "仅拆分", "仅校对", "仅生成PDF"],
            "add_file_title": "添加文件",
            "add_folder_title": "添加文件夹",
        }
        custom = getattr(self.subject_app, 'get_ui_features', lambda: {})()
        default_features.update(custom)
        return default_features

    def setup_ui(self):
        features = self._get_ui_features()

        self.mode_selector = ModeSelector(self.root, self.source_mode, self.exec_mode, self.on_mode_changed)
        self.mode_selector.set_source_options(features.get("show_source_modes", ["讲义", "试卷"]))
        self.mode_selector.set_exec_options(features.get("show_exec_modes", ["仅转换", "完整流程", "仅校对", "仅生成PDF"]))
        self.mode_selector.set_source_descriptions({
            "讲义": "讲义模式：处理 Word 讲义文档，支持清理表格、提取知识文件夹，适合同步讲义/备课资料校对。",
            "试卷": "试卷模式：处理 Word 试卷文档，按题号拆分校对，适合试卷/练习题校对。",
            "自由校对": "自由校对模式：直接粘贴文本或上传图片/文件，无需 Word 格式，适合零散内容快速校对。",
            "批注评审": "批注评审模式：提取 Word 文档中的批注，逐条评审批注质量并补充遗漏错误。",
        })
        self.mode_selector.set_exec_descriptions({
            "完整流程": "完整流程：转换 → 拆分 → 校对 → 生成报告，一键完成全部步骤。",
            "仅转换": "仅转换：只将 Word 文档转换为 Markdown，不拆分、不校对。",
            "仅拆分": "仅拆分：转换后按题目/板块拆分为多个单元，不进行校对。",
            "仅校对": "仅校对：对已拆分的题目目录进行 LLM 校对，需先完成拆分。",
            "仅生成PDF": "仅生成PDF：对已有校对结果的目录生成 LaTeX PDF 报告。",
        })

        self.frame_convert_settings = ttk.Frame(self.root, padding=10)
        self.frame_convert_settings.pack(fill=tk.X)

        self.setup_extra_options(self.frame_convert_settings)

        self.frame_split_mode = ttk.Frame(self.frame_convert_settings)
        if features.get("show_split_mode_option", False):
            self.frame_split_mode.pack(fill=tk.X, pady=(6, 0))
            ttk.Label(self.frame_split_mode, text="分割方式：").pack(side=tk.LEFT)
            self.combo_split = ttk.Combobox(self.frame_split_mode, textvariable=self.split_mode,
                                            values=["rule", "none", "smart", "manual"],
                                            state="readonly", width=12)
            self.combo_split.pack(side=tk.LEFT, padx=4)
            self.lbl_split_desc = ttk.Label(self.frame_split_mode, text="（普通规则）", foreground="gray")
            self.lbl_split_desc.pack(side=tk.LEFT, padx=4)
            self.combo_split.bind("<<ComboboxSelected>>", self._on_split_mode_changed)
            self._update_split_mode_desc()

        self.frame_output_dir = ttk.Frame(self.frame_convert_settings)
        ttk.Label(self.frame_output_dir, text="输出根目录：").pack(side=tk.LEFT)
        ttk.Entry(self.frame_output_dir, textvariable=self.output_dir, width=50).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(self.frame_output_dir, text="浏览", command=self.select_output_dir).pack(side=tk.LEFT)

        self.frame_pdf_options = ttk.Frame(self.frame_convert_settings)
        if features.get("show_pdf_option", True):
            self.frame_pdf_options.pack(fill=tk.X, pady=(6, 0))
            ttk.Checkbutton(self.frame_pdf_options, text="生成 LaTeX PDF 校对报告",
                            variable=self.generate_pdf).pack(side=tk.LEFT, padx=4)
        if features.get("show_parallel_option", True):
            if features.get("show_pdf_option", True):
                ttk.Checkbutton(self.frame_pdf_options, text="并行校对",
                                variable=self.parallel_enabled).pack(side=tk.LEFT, padx=4)
                ttk.Entry(self.frame_pdf_options, textvariable=self.parallel_count, width=3).pack(side=tk.LEFT)
                ttk.Label(self.frame_pdf_options, text="题/批").pack(side=tk.LEFT)

        self.frame_free_input = ttk.Frame(self.frame_convert_settings)
        self.btn_paste_text = ttk.Button(self.frame_free_input, text="📝 粘贴文本",
                                          command=self.paste_free_text)
        self.btn_add_images = ttk.Button(self.frame_free_input, text="🖼️ 上传图片",
                                          command=self.add_free_images)
        self.btn_add_free_files = ttk.Button(self.frame_free_input, text="📄 上传文件",
                                              command=self.add_free_files)
        self.lbl_free_status = ttk.Label(self.frame_free_input, text="未设置文本/图片/文件", foreground="gray")
        self.free_files = []

        self.frame_jy_options = ttk.Frame(self.frame_convert_settings)
        if features.get("show_clean_table_option", True) or features.get("show_knowledge_option", True):
            self.frame_jy_options.pack(fill=tk.X, pady=(6, 0))
            if features.get("show_clean_table_option", True):
                ttk.Checkbutton(self.frame_jy_options, text="清理表格边框",
                                variable=self.clean_enabled).pack(side=tk.LEFT, padx=4)
            if features.get("show_knowledge_option", True):
                ttk.Checkbutton(self.frame_jy_options, text="提取知识文件夹",
                                variable=self.knowledge_enabled).pack(side=tk.LEFT, padx=4)

        self.frame_file_area = ttk.Frame(self.root, padding=10)
        self.frame_file_area.pack(fill=tk.X)

        add_file_title = features.get("add_file_title", "添加文件")
        add_folder_title = features.get("add_folder_title", "添加文件夹")
        self.btn_add_files = ttk.Button(self.frame_file_area, text=f"📁 {add_file_title}",
                                        command=self.add_files)
        self.btn_add_folder = ttk.Button(self.frame_file_area, text=f"📂 {add_folder_title}",
                                         command=self.add_folder)
        self.btn_clear = ttk.Button(self.frame_file_area, text="🗑️ 清空列表", command=self.clear_list)
        self.btn_select_papers = ttk.Button(self.frame_file_area, text="🔍 选择试卷目录",
                                            command=self.select_single_paper)
        self.btn_select_root = ttk.Button(self.frame_file_area, text="📂 选择根目录",
                                          command=self.select_root_for_proofread)
        self.btn_select_pdf_folders = ttk.Button(self.frame_file_area, text="📂 选择拆分文件夹",
                                                  command=self.select_pdf_folders)

        self.btn_add_files.pack(side=tk.LEFT, padx=4)
        self.btn_add_folder.pack(side=tk.LEFT, padx=4)
        self.btn_clear.pack(side=tk.LEFT, padx=4)

        self.frame_list = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        self.frame_list.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.frame_list, text="待处理清单：").pack(anchor=tk.W)
        self.list_box = tk.Listbox(self.frame_list, height=6)
        self.list_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        frame_actions = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        frame_actions.pack(fill=tk.X)

        self.btn_action = ttk.Button(frame_actions, text="🚀 开始转换", command=self.start_conversion)
        self.btn_action.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(frame_actions, text="⏹️ 中断", command=self.interrupt_task, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_actions, text="📄 导出报告", command=self.export_report).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_actions, text="⚙️ API 配置", command=self.open_api_dialog).pack(side=tk.RIGHT, padx=4)

        self.log_panel = LogPanel(self.root)

        set_log_func(self._log)

    def setup_extra_options(self, frame):
        pass

    def _log(self, msg):
        self.log_panel.append(msg)

    def open_api_dialog(self):
        def on_save(url, key, model):
            save_env_config(self.subject_app.subject_dir, url, key, model)
            self.api_config = {"api_url": url, "api_key": key, "model_name": model}
            log("✅ API 配置已保存到 .env")

        ApiDialog(self.root, self.api_config, on_save)

    def _on_split_mode_changed(self, event=None):
        self._update_split_mode_desc()

    def _update_split_mode_desc(self):
        mode = self.split_mode.get()
        desc_map = {
            "rule": "（普通规则 - 按标题/题号拆分）",
            "none": "（不拆分 - 整份作为一个单元）",
            "smart": "（智能分割 - LLM 自动识别题目）",
            "manual": "（人工标记 - 按 ###### 标记拆分）",
        }
        desc = desc_map.get(mode, "")
        if hasattr(self, 'lbl_split_desc'):
            self.lbl_split_desc.config(text=desc)

    def paste_free_text(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("粘贴待校对文本")
        dialog.geometry("600x450")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="请粘贴或输入待校对的文本：", padding=10).pack(anchor=tk.W)
        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        if self.free_text:
            text_widget.insert("1.0", self.free_text)

        btn_frame = ttk.Frame(dialog, padding=(0, 0, 0, 10))
        btn_frame.pack(fill=tk.X)

        def _save():
            self.free_text = text_widget.get("1.0", tk.END).strip()
            self._update_free_status()
            dialog.destroy()

        ttk.Button(btn_frame, text="确定", command=_save).pack(side=tk.RIGHT, padx=10)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT)

    def add_free_images(self):
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"), ("所有文件", "*.*")]
        )
        if paths:
            added = 0
            for p in paths:
                if p not in self.free_images:
                    self.free_images.append(p)
                    added += 1
            self._update_free_status()
            log(f"🖼️ 已添加 {added} 张图片，共 {len(self.free_images)} 张")

    def add_free_files(self):
        paths = filedialog.askopenfilenames(
            title="选择文件（支持 md/txt/图片）",
            filetypes=[
                ("支持的文件", "*.md;*.txt;*.png;*.jpg;*.jpeg;*.gif;*.bmp"),
                ("Markdown/文本", "*.md;*.txt"),
                ("图片文件", "*.png;*.jpg;*.jpeg;*.gif;*.bmp"),
                ("所有文件", "*.*")
            ]
        )
        if paths:
            added = 0
            for p in paths:
                if p not in self.free_files:
                    self.free_files.append(p)
                    added += 1
            self._update_free_status()
            self.refresh_listbox()
            log(f"📄 已添加 {added} 个文件，共 {len(self.free_files)} 个")

    def _update_free_status(self):
        has_text = bool(self.free_text)
        has_images = len(self.free_images) > 0
        has_files = len(self.free_files) > 0
        parts = []
        if has_text:
            parts.append("文本")
        if has_images:
            parts.append(f"{len(self.free_images)}张图")
        if has_files:
            parts.append(f"{len(self.free_files)}个文件")
        if parts:
            status = "✅ 已设置 " + " + ".join(parts)
            color = "green"
        else:
            status = "未设置文本/图片/文件"
            color = "gray"
        self.lbl_free_status.config(text=status, foreground=color)

    def on_mode_changed(self):
        self.update_ui_for_mode()

    def update_ui_for_mode(self):
        exec_mode = self.exec_mode.get()
        source_mode = self.source_mode.get()
        is_proof_only = (exec_mode == "仅校对")
        is_pdf_only = (exec_mode == "仅生成PDF")
        is_free_mode = (source_mode == "自由校对")
        is_review_mode = (source_mode == "批注评审")
        features = self._get_ui_features()

        self.mode_selector.pack_forget_source()
        self.frame_convert_settings.pack_forget()
        self.frame_jy_options.pack_forget()
        self.frame_free_input.pack_forget()
        self.frame_split_mode.pack_forget() if hasattr(self, 'frame_split_mode') else None
        self.frame_output_dir.pack_forget()
        self.frame_pdf_options.pack_forget()

        self.btn_add_files.pack_forget()
        self.btn_add_folder.pack_forget()
        self.btn_clear.pack_forget()
        self.btn_select_papers.pack_forget()
        self.btn_select_root.pack_forget()
        self.btn_select_pdf_folders.pack_forget()

        if not is_pdf_only:
            self.mode_selector.pack_source(before=self.frame_file_area)

        if not is_proof_only and not is_pdf_only:
            self.frame_convert_settings.pack(fill=tk.X, before=self.frame_file_area)

            last_widget = None

            if source_mode == "讲义" and (features.get("show_clean_table_option", True) or features.get("show_knowledge_option", True)):
                if last_widget:
                    self.frame_jy_options.pack(fill=tk.X, after=last_widget, pady=(6, 0))
                else:
                    self.frame_jy_options.pack(fill=tk.X, pady=(6, 0))
                last_widget = self.frame_jy_options

            if is_free_mode:
                if last_widget:
                    self.frame_free_input.pack(fill=tk.X, after=last_widget, pady=(6, 0))
                else:
                    self.frame_free_input.pack(fill=tk.X, pady=(6, 0))
                self.btn_paste_text.pack(side=tk.LEFT, padx=4)
                self.btn_add_images.pack(side=tk.LEFT, padx=4)
                self.btn_add_free_files.pack(side=tk.LEFT, padx=4)
                self.lbl_free_status.pack(side=tk.LEFT, padx=10)
                last_widget = self.frame_free_input

            if features.get("show_split_mode_option", False) and hasattr(self, 'frame_split_mode'):
                if last_widget:
                    self.frame_split_mode.pack(fill=tk.X, after=last_widget, pady=(6, 0))
                else:
                    self.frame_split_mode.pack(fill=tk.X, pady=(6, 0))
                last_widget = self.frame_split_mode

            if last_widget:
                self.frame_output_dir.pack(fill=tk.X, after=last_widget, pady=(6, 0))
            else:
                self.frame_output_dir.pack(fill=tk.X, pady=(6, 0))
            last_widget = self.frame_output_dir

            if features.get("show_pdf_option", True) or features.get("show_parallel_option", True):
                if last_widget:
                    self.frame_pdf_options.pack(fill=tk.X, after=last_widget, pady=(6, 0))
                else:
                    self.frame_pdf_options.pack(fill=tk.X, pady=(6, 0))

        if is_pdf_only:
            self.btn_select_pdf_folders.pack(side=tk.LEFT, padx=4)
            self.btn_clear.pack(side=tk.LEFT, padx=4)
        elif is_proof_only:
            self.btn_select_papers.pack(side=tk.LEFT, padx=4)
            self.btn_select_root.pack(side=tk.LEFT, padx=4)
        elif is_free_mode:
            self.btn_clear.pack(side=tk.LEFT, padx=4)
        else:
            self.btn_add_files.pack(side=tk.LEFT, padx=4)
            self.btn_add_folder.pack(side=tk.LEFT, padx=4)
            self.btn_clear.pack(side=tk.LEFT, padx=4)

        if is_pdf_only:
            self.btn_action.config(text="📄 生成PDF", command=self.start_generate_pdf)
        elif is_proof_only:
            self.btn_action.config(text="🚀 开始校对", command=self.start_proofread)
        elif exec_mode == "完整流程":
            self.btn_action.config(text="🚀 开始处理", command=self.start_full_pipeline)
        elif exec_mode == "仅拆分":
            self.btn_action.config(text="✂️ 开始拆分", command=self.start_conversion)
        else:
            self.btn_action.config(text="📝 开始转换", command=self.start_conversion)

        self.refresh_listbox()

    def select_output_dir(self):
        path = filedialog.askdirectory(title="选择输出根目录")
        if path:
            self.output_dir.set(path)

    def add_files(self):
        filetypes = getattr(self.subject_app, 'get_supported_file_types',
                           lambda: [("支持的文件", "*.docx;*.doc;*.zip"),
                                    ("Word 文档", "*.docx;*.doc"),
                                    ("ZIP 压缩包", "*.zip"),
                                    ("所有文件", "*.*")])()
        paths = filedialog.askopenfilenames(
            title="选择文件或压缩包",
            filetypes=filetypes
        )
        added = 0
        for p in paths:
            if p.lower().endswith('.zip'):
                added += self._extract_zip(p)
            elif p not in self.file_list:
                self.file_list.append(p)
                added += 1
        self.refresh_listbox()
        log(f"📁 已添加 {added} 个文件")

    def _extract_zip(self, zip_path):
        try:
            out_dir = self.output_dir.get().strip() or DEFAULT_OUTPUT
            zip_basename = os.path.splitext(os.path.basename(zip_path))[0]
            extract_root = os.path.join(out_dir, "解压缩文件")
            extract_dir = os.path.join(extract_root, zip_basename)
            counter = 1
            while os.path.exists(extract_dir):
                extract_dir = os.path.join(extract_root, f"{zip_basename}_{counter}")
                counter += 1
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.infolist():
                    member_path = os.path.normpath(member.filename)
                    if member_path.startswith('..') or os.path.isabs(member_path):
                        log(f"   ⚠️ 跳过可疑条目: {member.filename}")
                        continue
                    zf.extract(member, extract_dir)
            found = 0
            supported_exts = getattr(self.subject_app, 'get_supported_extensions',
                                     lambda: {".docx", ".doc"})()
            for rt, _, files in os.walk(extract_dir):
                for name in files:
                    ext = os.path.splitext(name)[1].lower()
                    if ext in supported_exts:
                        full = os.path.join(rt, name)
                        if full not in self.file_list:
                            self.file_list.append(full)
                            found += 1
            log(f"   📦 解压到 {extract_dir}，找到 {found} 个文件")
            return found
        except Exception as e:
            log(f"   ❌ 解压失败 {os.path.basename(zip_path)}: {e}")
            return 0

    def add_folder(self):
        folder = filedialog.askdirectory(title="选择包含文档的文件夹")
        if not folder:
            return
        added = 0
        supported_exts = getattr(self.subject_app, 'get_supported_extensions',
                                 lambda: {".docx", ".doc"})()
        for rt, dirs, files in os.walk(folder):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext in supported_exts:
                    full = os.path.join(rt, name)
                    if full not in self.file_list:
                        self.file_list.append(full)
                        added += 1
        self.refresh_listbox()
        log(f"📂 从文件夹添加了 {added} 个文件")

    def clear_list(self):
        if self.exec_mode.get() in ("仅校对", "仅生成PDF"):
            self.proofread_list = []
            self.proofread_result = {}
            log("🗑️ 已清空清单")
        elif self.source_mode.get() == "自由校对":
            self.free_text = ""
            self.free_images = []
            self.free_files = []
            self._update_free_status()
            log("🗑️ 已清空文本、图片和文件")
        else:
            self.file_list = []
            log("🗑️ 已清空文件列表")
        self.refresh_listbox()

    @staticmethod
    def _natural_key(s):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

    def refresh_listbox(self):
        self.list_box.delete(0, tk.END)
        exec_mode = self.exec_mode.get()
        source_mode = self.source_mode.get()

        if exec_mode in ("仅校对", "仅生成PDF"):
            for i, (path, name) in enumerate(self.proofread_list, 1):
                self.list_box.insert(tk.END, f"{i}. {name}")
        elif source_mode == "自由校对":
            idx = 1
            if self.free_text:
                preview = self.free_text[:50].replace('\n', ' ')
                if len(self.free_text) > 50:
                    preview += "..."
                self.list_box.insert(tk.END, f"{idx}. 📝 文本: {preview}")
                idx += 1
            for img in self.free_images:
                self.list_box.insert(tk.END, f"{idx}. 🖼️  图片: {os.path.basename(img)}")
                idx += 1
            for f in self.free_files:
                ext = os.path.splitext(f)[1].lower()
                icon = "📄" if ext in ('.md', '.txt') else "🖼️"
                self.list_box.insert(tk.END, f"{idx}. {icon} 文件: {os.path.basename(f)}")
                idx += 1
            if idx == 1:
                self.list_box.insert(tk.END, "（未设置文本、图片或文件，请点击上方按钮添加）")
        else:
            sorted_files = sorted(self.file_list, key=lambda p: self._natural_key(os.path.basename(p)))
            for idx, path in enumerate(sorted_files, 1):
                self.list_box.insert(tk.END, f"{idx}. {os.path.basename(path)}")

    def select_single_paper(self):
        path = filedialog.askdirectory(title="选择单个试卷目录")
        if not path:
            return
        name = os.path.basename(path)
        entry = (path, name)
        if entry not in self.proofread_list:
            self.proofread_list.append(entry)
            self.refresh_listbox()
            log(f"🔍 已添加：{name}")
        else:
            log(f"   ⚠️ 已存在：{name}")

    def select_root_for_proofread(self):
        path = filedialog.askdirectory(title="选择试卷根目录（批量扫描子目录）")
        if not path:
            return
        dirs = self.subject_app.collect_paper_dirs(path)
        if not dirs:
            messagebox.showwarning("提示", "所选目录下没有识别到试卷结构（需包含第N题/板块N 或 知识 子目录）")
            return
        added = 0
        for d in dirs:
            name = os.path.basename(d)
            entry = (d, name)
            if entry not in self.proofread_list:
                self.proofread_list.append(entry)
                added += 1
        self.refresh_listbox()
        log(f"📂 已从根目录加载 {added} 套试卷到清单")

    def select_pdf_folders(self):
        paths = filedialog.askdirectory(title="选择拆分文件夹（含 第N题/板块N + _校对数据.json）")
        if not paths:
            return
        path = paths
        name = os.path.basename(path)
        subdirs = [e for e in os.listdir(path) if os.path.isdir(os.path.join(path, e))]
        has_questions = any(re.match(r'第\d+题|板块\d+', e) for e in subdirs)
        if not has_questions:
            messagebox.showwarning("提示", f"「{name}」下没有识别到题目目录（第N题/板块N），请确认选择正确")
            return
        entry = (path, name)
        if entry not in self.proofread_list:
            self.proofread_list.append(entry)
        self.refresh_listbox()
        log(f"📂 已添加拆分文件夹到清单：{name}")

    def start_generate_pdf(self):
        if not self.proofread_list:
            messagebox.showwarning("提示", "请先选择拆分文件夹（含 第N题/板块N + _校对数据.json）")
            return
        self.task_running = True
        self.task_interrupt = False
        self.btn_action.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.proofread_result = {}

        def _run():
            pdf_dir = os.path.join(self.output_dir.get(), "校对PDF")
            total = len(self.proofread_list)
            success = 0
            for i, (dir_path, paper_name) in enumerate(self.proofread_list):
                if self.task_interrupt:
                    log("\n===== 任务已中断 =====")
                    break
                log(f"\n📄 [{i+1}/{total}] 正在生成 PDF：{paper_name}")
                try:
                    pdf_path = generate_combined_pdf(dir_path, pdf_dir)
                    if pdf_path:
                        log(f"   ✅ PDF 已生成：{pdf_path}")
                        success += 1
                    else:
                        log(f"   ⚠️ 生成失败：未找到可用的校对数据")
                except Exception as e:
                    log(f"   ❌ 生成异常：{e}")
            if not self.task_interrupt:
                log(f"\n===== PDF 生成完成：{success}/{total} =====")
            self.task_running = False
            self.task_interrupt = False
            self.root.after(0, lambda: self.btn_action.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))

        threading.Thread(target=_run, daemon=True).start()

    def start_full_pipeline(self):
        self.start_conversion()

    def on_start_conversion(self):
        pass

    def on_start_proofread(self):
        pass

    def start_conversion(self):
        source_mode = self.source_mode.get()
        is_free_mode = (source_mode == "自由校对")

        if is_free_mode:
            if not self.free_text and not self.free_images and not self.free_files:
                messagebox.showwarning("提示", "请先粘贴文本、上传图片或上传文件")
                return
        else:
            if not self.file_list:
                messagebox.showwarning("提示", "请先添加文件")
                return

        out_dir = self.output_dir.get().strip()
        if not out_dir:
            out_dir = DEFAULT_OUTPUT
        if not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录: {e}")
                return

        if not is_free_mode:
            has_word = any(f.lower().endswith(('.docx', '.doc')) for f in self.file_list)
            if has_word and not check_pandoc():
                messagebox.showerror("错误", "检测到 Word 文件，但 Pandoc 未安装")
                return

            invalid = [f for f in self.file_list if ')' in os.path.basename(f)]
            if invalid:
                msg = "以下文件名包含 )，请重命名：\n\n" + "\n".join(os.path.basename(f) for f in invalid)
                messagebox.showerror("文件名错误", msg)
                log("❌ 文件名包含 ')'，已取消")
                return

        self.btn_action.config(state=tk.DISABLED)
        self.on_start_conversion()
        t = threading.Thread(target=self._conversion_thread, args=(out_dir,), daemon=True)
        t.start()

    def _conversion_thread(self, out_root):
        source = self.source_mode.get()
        exec_mode = self.exec_mode.get()
        split_mode = self.split_mode.get()
        is_free_mode = (source == "自由校对")
        is_review_mode = (source == "批注评审")

        log("=" * 50)

        split_root = os.path.join(out_root, "拆题结果")
        os.makedirs(split_root, exist_ok=True)

        converted_dirs = []

        if is_free_mode:
            log(f"开始转换，模式=自由校对")
            from shared.free_proofread import create_free_proofread_md
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            basename = f"自由校对_{ts}"

            temp_dir = os.path.join(out_root, "自由校对临时文件")
            os.makedirs(temp_dir, exist_ok=True)

            all_text_parts = []
            all_images = []

            if self.free_text:
                all_text_parts.append(self.free_text)

            all_images.extend(self.free_images)

            for fpath in self.free_files:
                ext = os.path.splitext(fpath)[1].lower()
                if ext in ('.md', '.txt'):
                    try:
                        with open(fpath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        all_text_parts.append(content)
                        log(f"   📄 已读取文件: {os.path.basename(fpath)}")
                    except Exception as e:
                        log(f"   ⚠️ 读取文件失败 {os.path.basename(fpath)}: {e}")
                elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
                    if fpath not in all_images:
                        all_images.append(fpath)
                        log(f"   🖼️  已添加图片: {os.path.basename(fpath)}")

            combined_text = "\n\n".join(all_text_parts) if all_text_parts else ""

            raw_md = create_free_proofread_md(combined_text, all_images, temp_dir)
            img_dir = os.path.join(temp_dir, f"{basename}_images")
            fname = basename
            needs_post = False

            if exec_mode == "仅转换":
                converted_dirs.append(os.path.dirname(raw_md))
                log(f"   ✅ 自由校对转换完成")
            else:
                log("   ✂️ 开始拆分...")
                options = {"split_mode": split_mode}
                if hasattr(self.subject_app, 'split_exam'):
                    split_ok = self.subject_app.split_exam(raw_md, split_root, basename, options)
                else:
                    split_ok = False

                if split_ok:
                    converted_dir = os.path.join(split_root, basename)
                    converted_dirs.append(converted_dir)
                    log(f"   ✅ 自由校对处理完成")
        else:
            total = len(self.file_list)
            log(f"开始转换，模式={source}，共 {total} 个文件")

            for idx, file_path in enumerate(self.file_list, 1):
                fname = os.path.basename(file_path)
                basename = os.path.splitext(fname)[0]
                ext = os.path.splitext(fname)[1].lower()

                target_base = basename
                counter = 1
                while os.path.exists(os.path.join(split_root, target_base)):
                    target_base = f"{basename}_{counter}"
                    counter += 1
                if target_base != basename:
                    log(f"   ⚠️ 目录重名：{basename} → {target_base}")
                    basename = target_base

                log(f"\n[{idx}/{total}] {fname}")
                file_dir = os.path.dirname(file_path)
                raw_md = os.path.join(file_dir, f"{basename}_raw.md")
                img_dir = os.path.join(file_dir, f"{basename}_images")

                is_md_file = (ext == '.md')

                if is_md_file:
                    try:
                        shutil.copy2(file_path, raw_md)
                        ok = True
                        needs_post = False
                        log("   📄 直接使用 Markdown 文件")
                    except Exception as e:
                        log(f"   ❌ 复制 md 文件失败: {e}")
                        ok = False
                else:
                    use_mathjax = (source == "讲义")
                    
                    convert_func = getattr(self.subject_app, 'convert_file_to_md', None)
                    if convert_func:
                        result = convert_func(file_path, raw_md, img_dir, use_mathjax=use_mathjax)
                        if isinstance(result, dict):
                            ok = result.get('success', False)
                            needs_post = result.get('needs_post_process', True)
                        else:
                            ok = result
                            needs_post = True
                    else:
                        ok = convert_with_pandoc(file_path, raw_md, img_dir, use_mathjax=use_mathjax)
                        needs_post = True
                
                if not ok:
                    log(f"   ❌ 转换失败")
                    continue

                if needs_post:
                    if source == "讲义":
                        fix_latex_escapes(raw_md)
                        if self.clean_enabled.get():
                            if clean_md_file(raw_md):
                                log("   ✅ 表格清理完成")
                            else:
                                log("   ⚠️ 表格清理失败")
                        fix_floating_images(raw_md)
                        normalize_option_spacing(raw_md)
                    else:
                        post_process_md_zw(raw_md)

                if is_review_mode and not is_md_file:
                    from shared.docx_comments import insert_comments_from_docx
                    try:
                        with open(raw_md, 'r', encoding='utf-8') as f:
                            md_content = f.read()
                        comment_md = insert_comments_from_docx(file_path, md_content)
                        with open(raw_md, 'w', encoding='utf-8') as f:
                            f.write(comment_md)
                        log("   📝 已提取 Word 批注")
                    except Exception as e:
                        log(f"   ⚠️ 批注提取失败：{e}")

                post_hook = getattr(self.subject_app, 'post_convert_hook', None)
                if post_hook:
                    post_hook(raw_md, source=source)

                if exec_mode == "仅转换":
                    converted_dirs.append(os.path.dirname(raw_md))
                    log(f"   ✅ {fname} 转换完成")
                    continue

                log("   ✂️ 开始拆分题目...")
                options = {"split_mode": split_mode}
                if source == "讲义":
                    options["do_clean"] = self.clean_enabled.get()
                    split_ok = self.subject_app.split_lecture(raw_md, split_root, basename, options)
                else:
                    split_ok = self.subject_app.split_exam(raw_md, split_root, basename, options)

                if split_ok:
                    if source == "讲义" and self.knowledge_enabled.get():
                        from core import config_loader
                        config_split_mode = config_loader.get_lecture_split_mode(self.subject_app.config)
                        if config_split_mode != "section":
                            self.subject_app.generate_knowledge(raw_md, split_root, basename)
                        else:
                            log("   📘 section 模式：跳过知识提取（版块即单元）")

                    converted_dir = os.path.join(split_root, basename)
                    converted_dirs.append(converted_dir)
                    log(f"   ✅ {fname} 处理完成")

        log("=" * 50)
        if exec_mode == "仅转换":
            log(f"✅ 转换完成，成功 {len(converted_dirs)} 个")
        else:
            log(f"✅ 拆分完成，成功 {len(converted_dirs)} 个")

        if exec_mode == "完整流程":
            if converted_dirs:
                log("\n📋 自动加载到校对清单...")
                for d in converted_dirs:
                    name = os.path.basename(d)
                    entry = (d, name)
                    if entry not in self.proofread_list:
                        self.proofread_list.append(entry)
                self.root.after(0, self.refresh_listbox)
                log(f"   已添加 {len(converted_dirs)} 套试卷，即将开始校对...")
                self.root.after(500, self.start_proofread)
            else:
                log("   ⚠️ 没有成功转换的文件，无法进入校对")
                self.root.after(0, lambda: self.btn_action.config(state=tk.NORMAL))
        else:
            self.root.after(0, lambda: self.btn_action.config(state=tk.NORMAL))

    def start_proofread(self):
        api_url = self.api_config.get("api_url", "")
        api_key = self.api_config.get("api_key", "")
        model = self.api_config.get("model_name", "")
        if not all([api_url, api_key, model]):
            messagebox.showerror("错误", "请先配置 API（点击 ⚙️ API 配置）")
            return
        if not self.proofread_list:
            messagebox.showwarning("提示", "校对清单为空，请先进行转换或选择试卷目录")
            return
        if self.task_running:
            return

        self.task_running = True
        self.task_interrupt = False
        self.btn_action.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.on_start_proofread()
        t = threading.Thread(target=self._proofread_thread, daemon=True)
        t.start()

    def interrupt_task(self):
        if self.task_running:
            self.task_interrupt = True
            log("===== 已触发中断 =====")

    def _proofread_thread(self):
        api_url = self.api_config.get("api_url", "")
        api_key = self.api_config.get("api_key", "")
        model = self.api_config.get("model_name", "")
        source_mode = self.source_mode.get()
        out_root = self.output_dir.get().strip()
        if not out_root:
            out_root = DEFAULT_OUTPUT
        report_root = os.path.join(out_root, "校对报告")
        os.makedirs(report_root, exist_ok=True)

        try:
            for paper_path, paper_name in self.proofread_list:
                if self.task_interrupt:
                    break
                log(f"\n>>>>>>>>>> 校对试卷：{paper_name} <<<<<<<<<<")
                paper_results = {}

                question_dirs = []
                knowledge_dir = None
                for item in os.listdir(paper_path):
                    full = os.path.join(paper_path, item)
                    if not os.path.isdir(full):
                        continue
                    if "题" in item or item.startswith("板块"):
                        question_dirs.append(full)
                    elif item == "知识":
                        knowledge_dir = full

                question_dirs.sort(key=lambda x: (
                    int(re.findall(r'\d+', os.path.basename(x))[0])
                    if re.findall(r'\d+', os.path.basename(x)) else 9999,
                    os.path.basename(x)))

                all_dirs = question_dirs[:]
                if knowledge_dir is not None:
                    all_dirs.append(knowledge_dir)

                skipped_dirs = []
                remaining_dirs = []
                for q_dir in all_dirs:
                    md_path = os.path.join(q_dir, "_校对报告.md")
                    json_path = os.path.join(q_dir, "_校对数据.json")
                    if os.path.exists(md_path) and os.path.exists(json_path):
                        try:
                            with open(md_path, 'r', encoding='utf-8') as f:
                                cached_result = f.read()
                            self.proofread_result[q_dir] = cached_result
                            paper_results[q_dir] = cached_result
                            skipped_dirs.append(q_dir)
                        except Exception:
                            remaining_dirs.append(q_dir)
                    else:
                        remaining_dirs.append(q_dir)

                if skipped_dirs:
                    log(f"   ⏭️  跳过已校对：{len(skipped_dirs)} 题")

                all_dirs = remaining_dirs

                generate_pdf = self.generate_pdf.get()
                use_parallel = self.parallel_enabled.get()
                try:
                    batch_size = int(self.parallel_count.get())
                    if batch_size < 1:
                        batch_size = 1
                except ValueError:
                    batch_size = BATCH_SIZE

                if use_parallel and len(all_dirs) > 1:
                    with ThreadPoolExecutor(max_workers=batch_size) as executor:
                        for batch_start in range(0, len(all_dirs), batch_size):
                            if self.task_interrupt:
                                break
                            batch = all_dirs[batch_start:batch_start + batch_size]
                            batch_num = batch_start // batch_size + 1
                            total_batches = (len(all_dirs) + batch_size - 1) // batch_size
                            log(f"  --- 第{batch_num}/{total_batches}批（{len(batch)}题）提交中 ---")

                            future_map = {}
                            for q_dir in batch:
                                q_name = os.path.basename(q_dir)
                                is_knowledge = (q_name == "知识")
                                task_type = "知识" if is_knowledge else "题目"
                                log(f"  ⏳ 提交{task_type}：{q_name}")
                                future = executor.submit(
                                    self.subject_app.proofread_one,
                                    api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf, source_mode
                                )
                                future_map[future] = (q_dir, q_name, is_knowledge)

                            for future in as_completed(future_map):
                                q_dir, q_name, is_knowledge = future_map[future]
                                task_type = "知识" if is_knowledge else "题目"
                                try:
                                    data = future.result()
                                    if data["success"]:
                                        self.proofread_result[q_dir] = data["result"]
                                        paper_results[q_dir] = data["result"]
                                        log(f"   ✅ {q_name} {task_type}校对完成")
                                    else:
                                        log(f"   ❌ {q_name} {task_type}校对失败：{data['error']}")
                                except Exception as e:
                                    log(f"   ❌ {q_name} 异常：{e}")

                            remaining = len(all_dirs) - (batch_start + len(batch))
                            if remaining > 0 and not self.task_interrupt:
                                log(f"  --- 第{batch_num}批完成，剩余{remaining}题 ---")
                else:
                    for q_dir in all_dirs:
                        if self.task_interrupt:
                            break
                        q_name = os.path.basename(q_dir)
                        is_knowledge = (q_name == "知识")
                        task_type = "知识" if is_knowledge else "题目"
                        log(f"校对{task_type}：{q_name}")
                        data = self.subject_app.proofread_one(
                            api_url, api_key, model, q_dir, q_name, is_knowledge, generate_pdf, source_mode
                        )
                        if data["success"]:
                            self.proofread_result[q_dir] = data["result"]
                            paper_results[q_dir] = data["result"]
                            log(f"   ✅ {q_name} 校对完成")
                        else:
                            log(f"   ❌ {q_name} 校对失败：{data['error']}")

                if not self.task_interrupt and paper_results:
                    self._export_paper_report(paper_name, paper_results, report_root)

                if self.generate_pdf.get() and not self.task_interrupt and paper_results:
                    try:
                        pdf_dir = os.path.join(self.output_dir.get(), "校对PDF")
                        pdf_path = generate_combined_pdf(paper_path, pdf_dir)
                        if pdf_path:
                            log(f"   📄 汇总 PDF：{pdf_path}")
                        else:
                            log(f"   ⚠️ 汇总 PDF 生成失败（无可用的校对数据）")
                    except Exception as e:
                        log(f"   ⚠️ 汇总 PDF 生成异常：{e}")

            if self.task_interrupt:
                log("\n===== 任务已中断 =====")
            else:
                log("\n===== 全部校对完成 =====")
        except Exception as e:
            log(f"❌ 任务异常：{e}")
        finally:
            self.task_running = False
            self.task_interrupt = False
            self.root.after(0, lambda: self.btn_action.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_stop.config(state=tk.DISABLED))

    def _export_paper_report(self, paper_name, paper_results, report_root):
        safe_name = "".join(c for c in paper_name if c not in r'\/:*?"<>|')
        report_path = os.path.join(report_root, f"{safe_name}_校对报告.md")
        report = f"# {paper_name} 校对报告\n\n"
        for q_path, content in paper_results.items():
            q_name = os.path.basename(q_path)
            report += f"## {q_name}\n{content}\n\n---\n\n"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        log(f"📄 已导出：{report_path}")

    def export_report(self):
        if not self.proofread_result:
            messagebox.showwarning("提示", "暂无校对结果")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md", filetypes=[("Markdown", "*.md")], title="保存校对报告"
        )
        if not path:
            return
        report = f"# {self.subject_app.name}校对总报告\n\n"
        for q_path, content in self.proofread_result.items():
            paper_name = os.path.basename(os.path.dirname(q_path))
            q_name = os.path.basename(q_path)
            report += f"## {paper_name} - {q_name}\n{content}\n\n---\n\n"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(report)
        messagebox.showinfo("成功", "报告导出完成")
