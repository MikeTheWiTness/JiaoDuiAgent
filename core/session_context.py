"""校对会话上下文 —— 封装 API 配置，消除参数传递链。"""
from dataclasses import dataclass, field


@dataclass
class SessionContext:
    """校对会话的不可变配置，在 UI 层构造，下游按需读取。"""

    api_url: str
    api_key: str
    model: str
    max_loops: int = 20
    max_tokens: int = 16384
    reasoning_effort: str = "high"
    output_dir: str | None = None
