"""结构化日志模块 —— 基于标准 logging，保留 UI 桥接兼容。

使用方式：
    from core.logging_utils import get_logger
    logger = get_logger(__name__)
    logger.info("消息")
    logger.warning("警告")
    logger.error("错误")

兼容旧代码：
    from core.logging_utils import log, set_log_func
    log("消息")        # → logger.info()
    set_log_func(fn)   # 注册 UI 面板回调
"""
import logging
import logging.handlers
import threading
from pathlib import Path

# ---- 内部状态 ----
_log_func = None
_log_lock = threading.Lock()
_initialized = False

# 日志格式：时间戳 | 级别 | 模块名 | 消息
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _UIBridgeHandler(logging.Handler):
    """将日志消息桥接到 UI 面板的回调函数。"""

    def emit(self, record: logging.LogRecord):
        global _log_func
        if _log_func:
            try:
                msg = self.format(record)
                with _log_lock:
                    _log_func(msg)
            except Exception:
                pass  # UI 回调失败不应中断主流程


def setup_logging(
    log_dir: Path = None,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    reset: bool = False,
):
    """初始化日志系统（应用启动时调用一次）。

    Args:
        log_dir: 日志文件目录，None 则仅输出到控制台 + UI
        level: 最低日志级别
        max_bytes: 单文件最大字节数（触发滚动）
        backup_count: 保留的历史日志文件数
        reset: 强制重新初始化（测试用）
    """
    global _initialized
    if _initialized and not reset:
        return

    root = logging.getLogger()
    root.setLevel(level)
    # 清除已有的 handlers（避免重复）
    root.handlers.clear()

    # 控制台输出
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # UI 桥接
    ui_handler = _UIBridgeHandler()
    ui_handler.setLevel(level)
    ui_handler.setFormatter(logging.Formatter("%(levelname)-7s | %(message)s"))
    root.addHandler(ui_handler)

    # 文件输出（按大小滚动）
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "app.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        root.addHandler(file_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取指定模块的 logger 实例。"""
    return logging.getLogger(name)


# ---- 兼容旧接口 ----

def set_log_func(func):
    """注册 UI 日志面板的回调函数（兼容旧代码）。"""
    global _log_func
    _log_func = func
    # 首次注册时自动初始化（使用默认配置）
    if not _initialized:
        setup_logging()


def log(msg: str):
    """输出一条 INFO 级别日志（兼容旧代码）。"""
    global _log_func
    # 旧路径：直接调用 UI 回调
    if _log_func and not _initialized:
        with _log_lock:
            _log_func(msg)
        return
    # 新路径：通过 logging 系统
    logger = get_logger("core")
    logger.info(msg)
