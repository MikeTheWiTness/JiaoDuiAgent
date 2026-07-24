"""校对会话上下文 —— 封装 API 配置，消除参数传递链。"""
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionContext:
    """校对会话的不可变配置，在 UI 层构造，下游按需读取。"""

    api_url: str
    api_key: str
    model: str
    max_loops: int = 20
    max_tokens: int = 16384
    reasoning_effort: str = "high"
    output_dir: str | None = None
    interrupt_event: threading.Event | None = None  # 中断信号

    @classmethod
    def from_credentials(
        cls,
        api_url: str,
        api_key: str,
        model: str,
        output_dir: str | None = None,
        max_loops: int = 3,
        max_tokens: int = 16384,
        reasoning_effort: str = "high",
    ) -> "SessionContext":
        """从散列凭证构造 SessionContext（供迁移中的旧调用方使用）。

        call_api 统一入口期望 ctx 参数；此工厂让尚未持有 ctx 的调用方
        （format_enforcement._bash_format_fix、smart_split._llm_call）
        无需了解 SessionContext 构造细节即可接入新签名。
        """
        return cls(
            api_url=api_url,
            api_key=api_key,
            model=model,
            output_dir=output_dir,
            max_loops=max_loops,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
