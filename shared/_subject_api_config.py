"""学科工具 API 凭证跨模块共享存储（线程安全）。

避免 physics_tools 与 chemistry_tools 各自维护 threading.local() 副本。
"""
import threading

_local = threading.local()


def set_subject_api_config(api_url: str, api_key: str, model: str, output_dir: str | None = None):
    """设置当前线程的 API 凭证。"""
    _local.value = {
        "api_url": api_url,
        "api_key": api_key,
        "model": model,
        "output_dir": output_dir,
    }


def get_subject_api_config() -> dict:
    """获取当前线程的 API 凭证。"""
    return getattr(_local, "value", {})
