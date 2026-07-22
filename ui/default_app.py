import os, re, json, base64, time, shutil, subprocess, threading, zipfile, sys, dataclasses
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path

from core.env_config import load_env_config, save_env_config
from core.logging_utils import set_log_func, log
from core.config_loader import clear_config_cache, load_config
from core.pandoc_utils import check_pandoc, convert_with_pandoc
from core.defaults import (
    fix_latex_escapes, clean_md_file, clean_intent_md_file, fix_floating_images,
    normalize_option_spacing, post_process_md_zw,
)
from shared.latex_generator import generate_combined_pdf
from shared.session import SessionManager
from core.session_context import SessionContext
from ui.widgets import LogPanel, ApiDialog
from ui.pipeline import PipelineBar, setup_pipeline_styles


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

        self.content_type = tk.StringVar(value="讲义")  # 讲义/试卷/自由校对/批注评审
        self.output_dir = tk.StringVar(value="output")

        self.clean_enabled = tk.BooleanVar(value=True)
        self.intent_clean_enabled = tk.BooleanVar(value=True)
        self.knowledge_enabled = tk.BooleanVar(value=True)

        self.generate_pdf = tk.BooleanVar(value=True)

        self.parallel_enabled = tk.BooleanVar(value=True)
        self.parallel_count = tk.StringVar(value="10")
        self.react_enabled = tk.BooleanVar(value=True)

        self.split_mode = tk.StringVar(value="普通规则")

        # 分割方式中文 ↔ 英文映射
        self.SPLIT_MODE_MAP = {
            "普通规则": "rule",
            "不拆分": "none",
            "智能分割": "smart",
            "人工标记": "manual",
        }
        self.free_text = ""
        self.free_images = []

        self.file_list = []
        self.proofread_list = []
        self.proofread_result = {}
        self.task_running = False
        self.task_interrupt = False
        self._interrupt_event = threading.Event()  # 线程间中断信号

        self.api_config = load_env_config(subject_app.subject_dir)

        # 清除配置缓存，确保最新的 config.json / agent_prompt.json 被加载
        clear_config_cache()
        subject_app.config = load_config(subject_app.subject_dir)

        # ReAct 初始状态（默认开启）
        self.subject_app.react_mode = True
        self.subject_app.tools = self.subject_app.build_tools()

        self.system_prompt = subject_app.get_question_prompt()
        self.tools = subject_app.tools

        self.setup_ui()
        self._update_ui_for_pipeline()

    def _get_ui_features(self):
        """获取学科自定义的 UI 功能开关。"""
        default_features = {
            "show_clean_table_option": True,
            "show_intent_clean_option": True,
            "show_knowledge_option": False,  # 统一模型下 LLM 自判类型，无需物理分离
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
        style = ttk.Style()
        setup_pipeline_styles(style)

        # ===== 管线 + 输出目录（始终可见） =====
        frame_top = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        frame_top.pack(fill=tk.X)
        ttk.Label(frame_top, text="管线：", font=("", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.pipeline = PipelineBar(frame_top, on_changed=self._on_pipeline_changed)
        self.pipeline.pack(side=tk.LEFT)
        # 输出目录
        ttk.Label(frame_top, text="  输出：").pack(side=tk.LEFT)
        ttk.Entry(frame_top, textvariable=self.output_dir, width=36).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_top, text="浏览", command=self.select_output_dir).pack(side=tk.LEFT)

        # ===== 导入选项 =====
        self.frame_import = ttk.LabelFrame(self.root, text="📥 导入选项", padding=10)
        frame_ct = ttk.Frame(self.frame_import)
        frame_ct.pack(fill=tk.X)
        ttk.Label(frame_ct, text="内容类型：").pack(side=tk.LEFT)
        for val, label in [("讲义", "讲义"), ("试卷", "试卷"), ("自由校对", "自由校对"), ("批注评审", "批注评审")]:
            ttk.Radiobutton(frame_ct, text=label, variable=self.content_type,
                           value=val, command=self._on_content_type_changed).pack(side=tk.LEFT, padx=4)

        # 讲义选项
        self.frame_jy_options = ttk.Frame(self.frame_import)
        if features.get("show_clean_table_option", True):
            ttk.Checkbutton(self.frame_jy_options, text="清理表格边框",
                            variable=self.clean_enabled).pack(side=tk.LEFT, padx=4)
        if features.get("show_knowledge_option", True):
            ttk.Checkbutton(self.frame_jy_options, text="提取知识文件夹",
                            variable=self.knowledge_enabled).pack(side=tk.LEFT, padx=4)

        # 自由校对输入
        self.frame_free_input = ttk.Frame(self.frame_import)
        self.btn_paste_text = ttk.Button(self.frame_free_input, text="📝 粘贴文本", command=self.paste_free_text)
        self.btn_add_images = ttk.Button(self.frame_free_input, text="🖼️ 上传图片", command=self.add_free_images)
        self.btn_add_free_files = ttk.Button(self.frame_free_input, text="📄 上传文件", command=self.add_free_files)
        self.lbl_free_status = ttk.Label(self.frame_free_input, text="未设置文本/图片/文件", foreground="gray")
        self.free_files = []

        # ===== 拆分选项 =====
        self.frame_split = ttk.LabelFrame(self.root, text="✂️ 拆分选项", padding=10)
        self.frame_split_mode = ttk.Frame(self.frame_split)
        if features.get("show_split_mode_option", False):
            self.frame_split_mode.pack(fill=tk.X)
            ttk.Label(self.frame_split_mode, text="分割方式：").pack(side=tk.LEFT)
            self.combo_split = ttk.Combobox(self.frame_split_mode, textvariable=self.split_mode,
                                            values=list(self.SPLIT_MODE_MAP.keys()),
                                            state="readonly", width=14)
            self.combo_split.pack(side=tk.LEFT, padx=4)
            self.lbl_split_desc = ttk.Label(self.frame_split_mode, text="（普通规则）", foreground="gray")
            self.lbl_split_desc.pack(side=tk.LEFT, padx=4)
            self.combo_split.bind("<<ComboboxSelected>>", self._on_split_mode_changed)
            self._update_split_mode_desc()

        # ===== 校对选项 =====
        self.frame_proof = ttk.LabelFrame(self.root, text="🔍 校对选项", padding=10)
        ttk.Checkbutton(self.frame_proof, text="ReAct 模式",
                        variable=self.react_enabled,
                        command=self._on_react_toggled).pack(side=tk.LEFT, padx=4)
        if features.get("show_parallel_option", True):
            ttk.Checkbutton(self.frame_proof, text="并行校对",
                            variable=self.parallel_enabled).pack(side=tk.LEFT, padx=4)
            ttk.Entry(self.frame_proof, textvariable=self.parallel_count, width=3).pack(side=tk.LEFT)
            ttk.Label(self.frame_proof, text="题/批").pack(side=tk.LEFT)

        # ===== 排版选项 =====
        self.frame_typeset = ttk.LabelFrame(self.root, text="📄 排版选项", padding=10)
        if features.get("show_pdf_option", True):
            ttk.Checkbutton(self.frame_typeset, text="生成 LaTeX PDF 校对报告",
                            variable=self.generate_pdf).pack(side=tk.LEFT, padx=4)

        # ===== 文件区域 =====
        self.frame_file_area = ttk.Frame(self.root, padding=(10, 4))
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

        self.frame_list = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        self.frame_list.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.frame_list, text="待处理清单（右键删除）：").pack(anchor=tk.W)
        self.list_box = tk.Listbox(self.frame_list, height=6)
        self.list_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self._setup_listbox_context_menu()

        frame_actions = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        frame_actions.pack(fill=tk.X)

        self.btn_action = ttk.Button(frame_actions, text="🚀 开始处理", command=self._on_action)
        self.btn_action.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(frame_actions, text="⏹️ 中断", command=self.interrupt_task, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_actions, text="📄 导出报告", command=self.export_report).pack(side=tk.LEFT, padx=4)
        ttk.Button(frame_actions, text="⚙️ API 配置", command=self.open_api_dialog).pack(side=tk.RIGHT, padx=4)

        self.log_panel = LogPanel(self.root)
        set_log_func(self._log)

        self._update_ui_for_pipeline()

    def _setup_listbox_context_menu(self):
        """为清单添加右键删除菜单。"""
        menu = tk.Menu(self.list_box, tearoff=0)
        menu.add_command(label="删除选中", command=self._delete_selected_from_list)
        menu.add_command(label="清空全部", command=self.clear_list)

        def _on_right_click(event):
            try:
                idx = self.list_box.nearest(event.y)
                if idx >= 0 and self.list_box.selection_includes(idx):
                    pass
                else:
                    self.list_box.selection_clear(0, tk.END)
                    if idx >= 0:
                        self.list_box.selection_set(idx)
            except Exception:
                pass
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        self.list_box.bind("<Button-3>", _on_right_click)
        self.list_box.bind("<Delete>", lambda e: self._delete_selected_from_list())

    def _delete_selected_from_list(self):
        """删除清单中选中的项。"""
        selected = self.list_box.curselection()
        if not selected:
            return
        # 从后往前删，避免索引偏移
        indices = sorted(selected, reverse=True)
        for idx in indices:
            path = self.list_box.get(idx)
            # 从内部列表中移除
            for lst in [self.file_list, self.proofread_list, self.free_files]:
                if path in lst:
                    lst.remove(path)
                    break
        self.refresh_listbox()
        log(f"🗑️ 已从清单中移除 {len(indices)} 项")

    # ===== 管线响应 =====

    def _on_pipeline_changed(self):
        """管线阶段切换时更新 UI。"""
        self._update_ui_for_pipeline()

    def _on_content_type_changed(self):
        """内容类型切换。"""
        self._update_ui_for_pipeline()

    def _update_ui_for_pipeline(self):
        """根据管线开关状态显示/隐藏对应阶段的选项面板。"""
        features = self._get_ui_features()
        import_active = self.pipeline.import_enabled
        split_active = self.pipeline.split_enabled
        proof_active = self.pipeline.proof_enabled
        typeset_active = self.pipeline.typeset_enabled
        content = self.content_type.get()
        is_lecture = (content == "讲义")
        is_free = (content == "自由校对")

        # 导入
        if import_active:
            self.frame_import.pack(fill=tk.X, padx=10, pady=(0, 2),
                                   before=self.frame_file_area)
        else:
            self.frame_import.pack_forget()

        # 讲义选项（导入 + 讲义）
        if import_active and is_lecture:
            self.frame_jy_options.pack(fill=tk.X, pady=(4, 0))
        else:
            self.frame_jy_options.pack_forget()

        # 自由校对输入（导入 + 自由校对）
        if import_active and is_free:
            self.frame_free_input.pack(fill=tk.X, pady=(4, 0))
            self.btn_paste_text.pack(side=tk.LEFT, padx=4)
            self.btn_add_images.pack(side=tk.LEFT, padx=4)
            self.btn_add_free_files.pack(side=tk.LEFT, padx=4)
            self.lbl_free_status.pack(side=tk.LEFT, padx=10)
        else:
            self.frame_free_input.pack_forget()

        # 拆分
        if split_active:
            self.frame_split.pack(fill=tk.X, padx=10, pady=(0, 2),
                                  before=self.frame_file_area)
        else:
            self.frame_split.pack_forget()

        # 校对
        if proof_active:
            self.frame_proof.pack(fill=tk.X, padx=10, pady=(0, 2),
                                  before=self.frame_file_area)
        else:
            self.frame_proof.pack_forget()

        # 排版
        if typeset_active:
            self.frame_typeset.pack(fill=tk.X, padx=10, pady=(0, 2),
                                    before=self.frame_file_area)
        else:
            self.frame_typeset.pack_forget()

        # 文件选择按钮
        self._hide_all_file_buttons()
        if not import_active:
            if split_active:
                # 从拆分开始：添加 MD 文件
                self.btn_add_files.config(text="📄 添加 MD 文件")
                self.btn_add_files.pack(side=tk.LEFT, padx=4)
                self.btn_add_folder.pack(side=tk.LEFT, padx=4)
                self.btn_clear.pack(side=tk.LEFT, padx=4)
            elif proof_active:
                self.btn_select_papers.config(text="📂 选择拆分文件夹")
                self.btn_select_papers.pack(side=tk.LEFT, padx=4)
                self.btn_select_root.pack(side=tk.LEFT, padx=4)
            elif typeset_active:
                self.btn_select_pdf_folders.pack(side=tk.LEFT, padx=4)
                self.btn_clear.pack(side=tk.LEFT, padx=4)
        elif is_free:
            self.btn_clear.pack(side=tk.LEFT, padx=4)
        else:
            self.btn_add_files.config(text=f"📁 {features.get('add_file_title', '添加文件')}")
            self.btn_add_files.pack(side=tk.LEFT, padx=4)
            self.btn_add_folder.pack(side=tk.LEFT, padx=4)
            self.btn_clear.pack(side=tk.LEFT, padx=4)

        self.refresh_listbox()

    def _hide_all_file_buttons(self):
        for btn in [self.btn_add_files, self.btn_add_folder, self.btn_clear,
                     self.btn_select_papers, self.btn_select_root, self.btn_select_pdf_folders]:
            btn.pack_forget()

    def _on_action(self):
        """校验管线组合合法性，然后路由到对应处理方法。"""
        imp = self.pipeline.import_enabled
        spl = self.pipeline.split_enabled
        prf = self.pipeline.proof_enabled
        typ = self.pipeline.typeset_enabled

        # 校验规则
        errors = []
        if imp and prf and not spl:
            errors.append("「校对」需要先「拆分」——校对器按拆分后的题目目录工作，不能直接校对原始文档。请同时勾选「拆分」。")
        if imp and typ and not prf:
            errors.append("「排版」需要校对结果——PDF 报告由校对报告生成。请同时勾选「校对」，或关闭「导入」后选择已有校对目录。")
        if not imp and not prf and not typ:
            errors.append("至少需要勾选一个阶段。")

        if errors:
            messagebox.showwarning("管线组合不合法", "\n\n".join(errors))
            return

        """根据管线状态路由到对应的处理方法。"""
        if not imp and not spl:
            if prf:
                self.start_proofread()
            elif typ:
                self.start_generate_pdf()
        elif spl and not prf:
            self.start_conversion()  # 仅拆分
        else:
            self.start_full_pipeline()  # 完整流程或仅转换

    def _on_react_toggled(self):
        enabled = self.react_enabled.get()
        self.subject_app.react_mode = enabled
        self.subject_app.tools = self.subject_app.build_tools()
        self.system_prompt = self.subject_app.get_question_prompt()
        log(f"ReAct 模式: {'ON' if enabled else 'OFF'}")

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

    def _split_mode_key(self):
        """返回当前分割方式对应的英文 key。"""
        return self.SPLIT_MODE_MAP.get(self.split_mode.get(), "rule")

    def _on_split_mode_changed(self, event=None):
        self._update_split_mode_desc()

    def _update_split_mode_desc(self):
        mode = self.split_mode.get()
        desc_map = {
            "普通规则": "按标题/题号自动拆分",
            "不拆分": "整份文档作为一个单元",
            "智能分割": "LLM 自动识别题目边界",
            "人工标记": "按 ###### 题目标记拆分",
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

    def select_output_dir(self):
        path = filedialog.askdirectory(title="选择输出根目录")
        if path:
            self.output_dir.set(path)

    def add_files(self):
        # 导入关 + 拆分开 → 仅接受 MD 文件（已有 MD，从拆分开始）
        if not self.pipeline.import_enabled:
            filetypes = [("Markdown 文件", "*.md"), ("所有文件", "*.*")]
            title = "选择 Markdown 文件"
        else:
            filetypes = getattr(self.subject_app, 'get_supported_file_types',
                               lambda: [("支持的文件", "*.docx;*.doc;*.md;*.zip"),
                                        ("Word 文档", "*.docx;*.doc"),
                                        ("Markdown 文件", "*.md"),
                                        ("ZIP 压缩包", "*.zip"),
                                        ("所有文件", "*.*")])()
            title = "选择文件或压缩包"
        paths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
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
        if not self.pipeline.import_enabled:
            self.proofread_list = []
            self.proofread_result = {}
            log("🗑️ 已清空清单")
        elif self.content_type.get() == "自由校对":
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
        import_enabled = self.pipeline.import_enabled
        content = self.content_type.get()

        if not import_enabled:
            for i, (path, name) in enumerate(self.proofread_list, 1):
                self.list_box.insert(tk.END, f"{i}. {name}")
        elif content == "自由校对":
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
            messagebox.showwarning("提示", "所选目录下没有识别到试卷结构（需包含 单元N/第N题/板块N 子目录）")
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
        paths = filedialog.askdirectory(title="选择拆分文件夹（含 单元N/第N题/板块N + _校对数据.json）")
        if not paths:
            return
        path = paths
        name = os.path.basename(path)
        subdirs = [e for e in os.listdir(path) if os.path.isdir(os.path.join(path, e))]
        has_questions = any(re.match(r'第\d+题|板块\d+|单元\d+', e) for e in subdirs)
        if not has_questions:
            messagebox.showwarning("提示", f"「{name}」下没有识别到题目目录（单元N/第N题/板块N），请确认选择正确")
            return
        entry = (path, name)
        if entry not in self.proofread_list:
            self.proofread_list.append(entry)
        self.refresh_listbox()
        log(f"📂 已添加拆分文件夹到清单：{name}")

    def start_generate_pdf(self):
        if not self.proofread_list:
            messagebox.showwarning("提示", "请先选择拆分文件夹（含 单元N/第N题/板块N + _校对数据.json）")
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
        content = self.content_type.get()
        is_free_mode = (content == "自由校对")

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
        source = self.content_type.get()
        do_split = self.pipeline.split_enabled
        do_proof = self.pipeline.proof_enabled
        split_mode = self._split_mode_key()
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

            if not do_split:
                converted_dirs.append(os.path.dirname(raw_md))
                log(f"   ✅ 自由校对转换完成")
            else:
                log("   ✂️ 开始拆分...")
                options = {"split_mode": split_mode,
                          "api_url": self.api_config.get("api_url", ""),
                          "api_key": self.api_config.get("api_key", ""),
                          "model": self.api_config.get("model_name", "")}
                if hasattr(self.subject_app, 'split_exam'):
                    try:
                        split_ok = self.subject_app.split_exam(raw_md, split_root, basename, options)
                    except Exception as e:
                        log(f"❌ 拆分失败：{e}")
                        split_ok = False
                else:
                    split_ok = False

                if split_ok:
                    converted_dir = os.path.join(split_root, basename)
                    converted_dirs.append(converted_dir)
                    log(f"   ✅ 自由校对处理完成")
                else:
                    log(f"   ⚠️ 自由校对拆分未完成，跳过")
        else:
            total = len(self.file_list)
            log(f"开始转换，模式={source}，共 {total} 个文件")

            for idx, file_path in enumerate(self.file_list, 1):
                fname = os.path.basename(file_path)
                basename = os.path.splitext(fname)[0].strip()
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

                # 批注评审模式：转换前往 docx 注入占位符，让批注按 docx 真实位置就位
                convert_source = file_path
                temp_docx_path = None
                if is_review_mode and not is_md_file and ext in ('.docx', '.doc'):
                    try:
                        from shared.docx_comments import inject_comment_placeholders
                        temp_docx_path = inject_comment_placeholders(file_path)
                        if temp_docx_path:
                            convert_source = temp_docx_path
                    except Exception as e:
                        log(f"   ⚠️ 批注占位符注入失败，回退原文件：{e}")

                if is_md_file:
                    try:
                        shutil.copy2(file_path, raw_md)
                        ok = True
                        needs_post = False
                        log("   📄 直接使用 Markdown 文件（跳过转换，后处理保持原样）")
                    except Exception as e:
                        log(f"   ❌ 复制 md 文件失败: {e}")
                        ok = False
                else:
                    use_mathjax = (source == "讲义")
                    
                    convert_func = getattr(self.subject_app, 'convert_file_to_md', None)
                    if convert_func:
                        result = convert_func(convert_source, raw_md, img_dir, use_mathjax=use_mathjax)
                        if isinstance(result, dict):
                            ok = result.get('success', False)
                            needs_post = result.get('needs_post_process', True)
                        else:
                            ok = result
                            needs_post = True
                    else:
                        ok = convert_with_pandoc(convert_source, raw_md, img_dir, use_mathjax=use_mathjax)
                        needs_post = True

                # temp docx 已被 pandoc 读取完毕，清理（成功/失败都清）
                if temp_docx_path:
                    try:
                        os.unlink(temp_docx_path)
                    except OSError:
                        pass
                    temp_docx_path = None

                if not ok:
                    log(f"   ❌ 转换失败")
                    continue

                # Word 格式增强：提取着重号、下划线、波浪线、删除线等特殊格式
                if not is_md_file and ext in ('.docx', '.doc'):
                    from core.pandoc_utils import enhance_docx_conversion
                    enhance_docx_conversion(file_path, raw_md)

                if needs_post:
                    if source == "讲义":
                        fix_latex_escapes(raw_md)
                        if self.clean_enabled.get():
                            if clean_md_file(raw_md):
                                log("   ✅ 表格清理完成")
                            else:
                                log("   ⚠️ 表格清理失败")
                        if self.intent_clean_enabled.get():
                            from core.defaults import get_intent_problem_markers
                            markers = get_intent_problem_markers(self.subject_app.config)
                            if clean_intent_md_file(raw_md, problem_markers=markers):
                                log("   ✅ 出题意图清理完成")
                            else:
                                log("   ⚠️ 出题意图清理失败")
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

                if not do_split:
                    converted_dirs.append(os.path.dirname(raw_md))
                    log(f"   ✅ {fname} 转换完成")
                    continue

                log("   ✂️ 开始拆分题目...")
                options = {"split_mode": split_mode,
                          "api_url": self.api_config.get("api_url", ""),
                          "api_key": self.api_config.get("api_key", ""),
                          "model": self.api_config.get("model_name", "")}
                if source == "讲义":
                    options["do_clean"] = self.clean_enabled.get()
                try:
                    if source == "讲义":
                        split_ok = self.subject_app.split_lecture(raw_md, split_root, basename, options)
                    else:
                        split_ok = self.subject_app.split_exam(raw_md, split_root, basename, options)
                except Exception as e:
                    log(f"❌ 拆分失败：{e}")
                    split_ok = False

                if split_ok:
                    # ADR-0017: section 模式下知识自然成板块，不再需要独立知识提取
                    log("   📘 section 模式：知识已作为独立板块，跳过旧版知识提取")

                    converted_dir = os.path.join(split_root, basename)
                    converted_dirs.append(converted_dir)
                    log(f"   ✅ {fname} 处理完成")
                else:
                    log(f"   ⚠️ {fname} 拆分未完成，跳过")

        log("=" * 50)
        if not do_split:
            log(f"✅ 转换完成，成功 {len(converted_dirs)} 个")
        else:
            log(f"✅ 拆分完成，成功 {len(converted_dirs)} 个")

        if do_proof:
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
            self._interrupt_event.set()  # 通知所有线程中断
            log("===== 已触发中断（取消进行中的请求） =====")

    def _proofread_thread(self):
        api_url = self.api_config.get("api_url", "")
        api_key = self.api_config.get("api_key", "")
        model = self.api_config.get("model_name", "")
        content = self.content_type.get()
        out_root = self.output_dir.get().strip()
        if not out_root:
            out_root = DEFAULT_OUTPUT
        # 重置中断信号
        self._interrupt_event.clear()
        ctx = SessionContext(
            api_url=api_url, api_key=api_key, model=model,
            max_loops=self.subject_app.get_max_tool_loops(),
            output_dir=out_root,
            interrupt_event=self._interrupt_event,
        )
        report_root = os.path.join(out_root, "校对报告")
        os.makedirs(report_root, exist_ok=True)

        try:
            for paper_path, paper_name in self.proofread_list:
                if self.task_interrupt:
                    break
                log(f"\n>>>>>>>>>> 校对试卷：{paper_name} <<<<<<<<<<")
                paper_results = {}

                question_dirs = []
                for item in os.listdir(paper_path):
                    full = os.path.join(paper_path, item)
                    if not os.path.isdir(full):
                        continue
                    if item.startswith("单元"):
                        # ADR-0017: 统一命名为 单元N
                        question_dirs.append(full)
                    elif "题" in item or item.startswith("板块"):
                        # 向后兼容旧命名
                        question_dirs.append(full)
                    elif item == "知识":
                        # 向后兼容旧知识目录
                        question_dirs.append(full)

                question_dirs.sort(key=lambda x: (
                    int(re.findall(r'\d+', os.path.basename(x))[0])
                    if re.findall(r'\d+', os.path.basename(x)) else 9999,
                    os.path.basename(x)))

                all_dirs = question_dirs

                skipped_dirs = []
                remaining_dirs = []
                for q_dir in all_dirs:
                    # ADR-0017 决策9：跳过带 .skip_proofread 标记的导航单元
                    if os.path.exists(os.path.join(q_dir, ".skip_proofread")):
                        log(f"   ⏭️ {os.path.basename(q_dir)} 标记为跳过校对")
                        skipped_dirs.append(q_dir)
                        continue
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

                # Session 持久化：记录校对进度，支持中断恢复
                session_mgr = SessionManager(Path(out_root) / "sessions")
                q_list = [{"name": os.path.basename(d), "dir": d} for d in all_dirs]
                session_id = session_mgr.start_session(
                    f"{self.subject_app.name} - {paper_name}", q_list)
                log(f"   📝 Session: {session_id}")

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
                                log(f"  ⏳ 提交单元：{q_name}")
                                unit_ctx = dataclasses.replace(ctx, output_dir=q_dir)
                                future = executor.submit(
                                    self.subject_app.proofread_one,
                                    unit_ctx, q_dir, q_name, generate_pdf, content
                                )
                                future_map[future] = (q_dir, q_name)

                            for future in as_completed(future_map):
                                if self.task_interrupt:
                                    # 取消所有未完成的 future
                                    for f in future_map:
                                        if not f.done():
                                            f.cancel()
                                    break
                                q_dir, q_name = future_map[future]
                                try:
                                    data = future.result()
                                    if data is None:
                                        raise ValueError("proofread_one 返回了 None（内部缺少 return 语句？）")
                                    if data["success"]:
                                        self.proofread_result[q_dir] = data["result"]
                                        paper_results[q_dir] = data["result"]
                                        session_mgr.mark_completed(q_name)
                                        log(f"   ✅ {q_name} 校对完成")
                                    else:
                                        session_mgr.mark_failed(q_name, data.get('error', ''))
                                        log(f"   ❌ {q_name} 校对失败：{data['error']}")
                                except Exception as e:
                                    session_mgr.mark_failed(q_name, str(e))
                                    log(f"   ❌ {q_name} 异常：{e}")

                            remaining = len(all_dirs) - (batch_start + len(batch))
                            if remaining > 0 and not self.task_interrupt:
                                log(f"  --- 第{batch_num}批完成，剩余{remaining}题 ---")
                else:
                    for q_dir in all_dirs:
                        if self.task_interrupt:
                            break
                        q_name = os.path.basename(q_dir)
                        log(f"校对单元：{q_name}")
                        unit_ctx = dataclasses.replace(ctx, output_dir=q_dir)
                        data = self.subject_app.proofread_one(
                            unit_ctx, q_dir, q_name, generate_pdf, content
                        )
                        if data is None:
                            log(f"   ❌ {q_name} 校对失败：proofread_one 返回了 None")
                            session_mgr.mark_failed(q_name, "proofread_one 返回了 None")
                            continue
                        if data["success"]:
                            self.proofread_result[q_dir] = data["result"]
                            paper_results[q_dir] = data["result"]
                            session_mgr.mark_completed(q_name)
                            log(f"   ✅ {q_name} 校对完成")
                        else:
                            session_mgr.mark_failed(q_name, data.get('error', ''))
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
            import traceback
            log(f"❌ 任务异常：{e}\n{traceback.format_exc()}")
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
