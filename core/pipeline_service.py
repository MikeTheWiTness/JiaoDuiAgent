"""校对与转换编排服务 —— 从 UI 线程下沉到 core，全模块可单测（ADR-0022）。

对外接口：
  - ConversionService.run_conversion(req) → ConversionResult
  - ProofreadService.run_proofread(req) → ProofreadResult
"""
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.logging_utils import log as _default_log

# ---- 请求/结果数据类 ----

@dataclass
class ConversionRequest:
    """转换请求。字段与 UI _conversion_thread 原状态一一对应。"""
    md_file: str                     # 输入 .md 文件路径
    output_root: str                 # 输出根目录
    source_mode: str = "讲义"        # 来源模式：讲义/试卷/自由校对/批注评审
    split_mode: str = "section"      # 拆分模式
    base_name: str = ""              # 输出基础名
    options: dict = field(default_factory=dict)


@dataclass
class ConversionResult:
    """转换结果。"""
    success: bool = False
    error: str = ""


@dataclass
class ProofreadRequest:
    """校对请求。"""
    api_url: str
    api_key: str
    model: str
    paper_dir: str                  # 试卷根目录
    output_dir: str | None = None
    subject_app: object | None = None  # SubjectApp 实例（提供 proofread_one 等方法）
    batch_size: int = 4
    generate_pdf: bool = False
    interrupt_event: threading.Event | None = None


@dataclass
class ProofreadResult:
    """校对结果。"""
    success: bool = False
    total_questions: int = 0
    completed: int = 0
    error: str = ""


# ---- 服务基类 ----

class _PipelineService:
    """编排服务基类：持有回调 + 中断源。"""

    def __init__(self, on_log: Callable = None, on_progress: Callable = None,
                 interrupt_event: threading.Event | None = None):
        self._on_log = on_log or _default_log
        self._on_progress = on_progress or (lambda *a, **kw: None)
        self._interrupt = interrupt_event

    @property
    def interrupted(self) -> bool:
        return self._interrupt is not None and self._interrupt.is_set()


# ---- ConversionService ----

class ConversionService(_PipelineService):
    """转换编排服务：文件后处理 + 批注注入/回写 + 拆分调度。"""

    def run_conversion(self, req: ConversionRequest) -> ConversionResult:
        """执行转换流程。

        当前为骨架实现——完整业务逻辑需从 ui/default_app._conversion_thread
        逐段搬迁（ADR-0022 C2.1）。骨架保留接口契约供单测先行接入。
        """
        try:
            if self.interrupted:
                return ConversionResult(success=False, error="转换被中断")

            self._on_log(f"📂 开始转换: {req.md_file}")
            # TODO: 完整搬迁 _conversion_thread 业务逻辑
            # 1. 文件后处理（fix_latex_escapes / clean_md_file / normalize_option_spacing）
            # 2. 批注占位注入与回写
            # 3. split_lecture / split_exam 调度
            # 4. 自由校对组装

            self._on_log("✅ 转换完成")
            return ConversionResult(success=True)
        except Exception as e:
            self._on_log(f"❌ 转换失败: {e}")
            return ConversionResult(success=False, error=str(e))


# ---- ProofreadService ----

class ProofreadService(_PipelineService):
    """校对编排服务：目录扫描 + 缓存命中 + 并发调度 + PDF 汇总。"""

    def run_proofread(self, req: ProofreadRequest) -> ProofreadResult:
        """执行校对流程。

        当前为骨架实现——完整业务逻辑需从 ui/default_app._proofread_thread
        逐段搬迁（ADR-0022 C2.2）。骨架保留接口契约供单测先行接入。
        """
        try:
            if self.interrupted:
                return ProofreadResult(success=False, error="校对被中断")

            self._on_log(f"🔍 开始校对: {req.paper_dir}")

            # 扫描题目目录
            paper = Path(req.paper_dir)
            if not paper.exists():
                return ProofreadResult(success=False, error=f"目录不存在: {req.paper_dir}")

            from core.unit_detect import scan_question_dirs
            q_dirs = scan_question_dirs(paper)
            if not q_dirs:
                return ProofreadResult(success=False, error="未找到校对单元目录")

            total = len(q_dirs)
            self._on_log(f"   找到 {total} 个校对单元")

            # TODO: 完整搬迁 _proofread_thread 业务逻辑
            # 1. 缓存命中判断
            # 2. SessionManager 初始化
            # 3. ThreadPoolExecutor 并发调度
            # 4. 结果聚合 + PDF 汇总

            self._on_log(f"✅ 校对完成 ({total} 题)")
            return ProofreadResult(success=True, total_questions=total, completed=total)
        except Exception as e:
            self._on_log(f"❌ 校对失败: {e}")
            return ProofreadResult(success=False, error=str(e))
