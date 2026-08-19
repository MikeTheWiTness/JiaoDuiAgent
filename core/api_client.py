import json
import os
import time
import traceback
from dataclasses import dataclass, field

import requests

from core.logging_utils import log

MAX_RETRY = 2
# 超时设置：(连接超时, 读取超时)
# - 连接超时 30s：建立 TCP/TLS 连接的上限，绰绰有余
# - 读取超时 1800s（30 分钟）：推理模型（如 deepseek-v4-pro + reasoning_effort=high）
#   单次思考可能超过 10 分钟，加上工具调用循环，30 分钟是合理上限
TIME_OUT = (30, 1800)
MAX_FILE_SIZE = 10 * 1024 * 1024

# API 格式常量
API_FORMAT_CHAT_COMPLETIONS = "chat/completions"
API_FORMAT_RESPONSES = "responses"

# 工具分类常量（供工具循环熔断/配额逻辑使用）
_SEARCH_TOOLS = {"web_search", "web_fetch"}
_MAX_SEARCH = 5
_NAV_CONTROL_TOOLS = {
    "plan_update", "locate_paragraph", "read_section",
    "read_file", "write_file", "independent_solve",
}

# ---- 异常层级 ----

class ProofreadError(Exception):
    """校对流程异常基类。"""
    def __init__(self, message: str, status_code: int = None, retryable: bool = True):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class APITimeoutError(ProofreadError):
    """API 请求超时或连接错误。可重试。"""
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message, status_code=status_code, retryable=True)
        self.backoff_base = 2.0


class APIRateLimitError(ProofreadError):
    """API 限流错误（HTTP 429）。可重试，退避更长。"""
    def __init__(self, message: str, status_code: int = 429, retry_after: int = None):
        super().__init__(message, status_code=status_code, retryable=True)
        self.retry_after = retry_after
        self.backoff_base = 5.0


class APIAuthError(ProofreadError):
    """API 认证/鉴权错误（HTTP 401/403）。不可重试。"""
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message, status_code=status_code, retryable=False)


class APIBadRequestError(ProofreadError):
    """API 请求格式错误（HTTP 400）。不可重试——请求本身有问题，重试不会成功。"""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message, status_code=status_code, retryable=False)


class FormatError(ProofreadError):
    """校对输出格式错误。由格式审查层处理，不触发 API 重试。"""
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class ToolExecutionError(ProofreadError):
    """工具执行异常。记录后继续流程，不中断。"""
    def __init__(self, message: str, tool_name: str = None):
        super().__init__(message, retryable=False)
        self.tool_name = tool_name


def _classify_error(exc: Exception) -> ProofreadError:
    """将原始异常分类为校对异常层级。"""
    # requests 超时 → 区分连接超时（网络）和读取超时（模型慢）
    if isinstance(exc, requests.exceptions.Timeout):
        if isinstance(exc, requests.exceptions.ConnectTimeout):
            return APITimeoutError(f"连接超时（无法建立连接）: {exc}")
        if isinstance(exc, requests.exceptions.ReadTimeout):
            return APITimeoutError(
                f"读取超时（模型响应太慢，当前超时上限: 连接{TIME_OUT[0]}s / 读取{TIME_OUT[1]}s）: {exc}"
            )
        return APITimeoutError(str(exc))
    if isinstance(exc, requests.exceptions.ConnectionError):
        return APITimeoutError(str(exc))

    # HTTP 错误 → 按状态码细分
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, 'response', None)
        if response is not None:
            status = response.status_code
            msg = f"HTTP {status}: {response.text[:200]}"
            if status == 400:
                return APIBadRequestError(msg, status_code=status)
            if status == 429:
                retry_after = None
                try:
                    retry_after = int(response.headers.get("Retry-After", 0))
                except (ValueError, TypeError):
                    pass
                return APIRateLimitError(msg, status_code=status, retry_after=retry_after)
            if status in (401, 403):
                return APIAuthError(msg, status_code=status)
        return ProofreadError(str(exc))

    # 请求异常（其他）
    if isinstance(exc, requests.exceptions.RequestException):
        return ProofreadError(str(exc))

    # 未知异常
    return ProofreadError(f"未知错误: {exc}")


def _should_retry(error: ProofreadError) -> bool:
    """判断是否应该重试。"""
    return getattr(error, 'retryable', True)


def _backoff_delay(retry_count: int, base: float = 2.0, max_delay: float = 30.0) -> float:
    """计算指数退避延迟（秒）。

    delay = base * 2^retry_count，上限 max_delay。
    """
    delay = base * (2 ** retry_count)
    return min(delay, max_delay)


def _model_supports_reasoning_effort(model: str) -> bool:
    """判断模型是否支持 reasoning_effort 参数。

    reasoning_effort 是推理模型特有的参数（OpenAI o-series / DeepSeek Reasoner / V4 等）。
    已知不支持的模型：
    - deepseek-chat（V3 系列，纯 chat 模型，传了会返回 HTTP 400）

    其他模型默认发送——如果不支持，API 会返回 400，响应体会写明原因。
    """
    # 仅 deepseek-chat（V3）明确不支持
    if model.startswith("deepseek-chat"):
        return False
    # 其余模型默认发送（deepseek-reasoner、deepseek-v4-pro、doubao 等均支持或忽略）
    return True


def _model_supports_images(model: str) -> bool:
    """判断模型是否支持图片输入（vision / multimodal）。

    纯文本模型不支持 `image_url` 类型的消息内容，发送图片会导致 HTTP 400：
    `unknown variant 'image_url', expected 'text'`

    已知纯文本模型：
    - deepseek-reasoner（R1 推理模型）
    - deepseek-v4-pro（V4 推理模型）
    - deepseek-v* 系列
    """
    TEXT_ONLY_PREFIXES = [
        "deepseek-reasoner",   # R1 推理模型，纯文本
    ]
    for prefix in TEXT_ONLY_PREFIXES:
        if model.startswith(prefix):
            return False
    # deepseek-v 系列（v4-pro 等）是纯文本推理模型
    if model.startswith("deepseek-v"):
        return False
    # 其他模型（deepseek-chat、doubao、gpt-4o 等）默认支持图片
    return True


# ---- StopReason ----

class StopReason:
    """call_api 的显式停止原因，替代隐式 finish_reason 判断。"""
    END_TURN = "end_turn"         # LLM 返回了文本（不含 tool_calls），自然结束
    TOOL_LOOP = "tool_loop"       # 连续 3 轮空/重复结果，触发压缩
    MAX_TURNS = "max_turns"       # max_loops 触顶，触发压缩
    ERROR = "error"               # API 调用异常
    INTERRUPTED = "interrupted"   # 用户中断


# ---- LoopResult（C2）----

@dataclass
class LoopResult:
    """工具循环退出结果。stop_reason 复用 StopReason 常量。"""
    content: str = ""
    reasoning: str = ""
    messages: list = field(default_factory=list)
    stop_reason: str = ""
    tool_calls_log: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    reasonings: dict = field(default_factory=dict)  # {assistant 轮次: reasoning_content}，落盘对话记录用

    def as_dict(self) -> dict:
        """转为与 call_api 对外返回一致的 6 key dict，key 集合及顺序逐字不变。"""
        return {
            "content": self.content,
            "tool_calls_log": self.tool_calls_log,
            "reasoning": self.reasoning,
            "messages": self.messages,
            "stop_reason": self.stop_reason,
            "usage": self.usage,
        }


@dataclass
class ProofreadState:
    """工具循环全部可变状态的唯一载体（ADR-0029：快照 = dump() / 续跑 = load()）。

    循环计数器、记录器、突变后的 openai_tools、累计用量全收拢在此；
    `payload` 不入 state——纯派生件，循环内每轮由 ctx + state 重建（见 _build_payload）。
    `choice` 为当前轮 LLM 响应（瞬态，不随快照序列化）。
    """
    messages: list = field(default_factory=list)
    loop: int = 0
    search_count: int = 0
    empty_streak: int = 0
    recent_results: list = field(default_factory=list)
    tool_calls_log: list = field(default_factory=list)
    reasonings: dict = field(default_factory=dict)   # {assistant 轮次: reasoning_content}
    assistant_turn: int = 0
    openai_tools: list | None = None                # 搜索配额耗尽/压缩后可能已移除工具
    reasoning_effort: str | None = None
    total_usage: dict = field(default_factory=lambda: {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    })
    initial_header: str = ""
    # 当前轮 LLM 响应（瞬态，不入快照）
    choice: dict | None = field(default=None, repr=False)


# ---- 工具定义 ----

def tool_to_openai(tool):
    schema = tool.args_schema.model_json_schema()
    params = {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
    }
    # 包含 $defs 定义，使嵌套 Pydantic 模型的 $ref 能正确解析
    # 如 PlanUpdateTool 的 PlanItem → $ref: "#/$defs/PlanItem" 需要 $defs 段
    if "$defs" in schema:
        params["$defs"] = schema["$defs"]
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": params,
        }
    }


def _normalize_api_format(api_format: str) -> str:
    """归一化 API 格式值，兼容 `responses` 与 `/responses` 两种写法。"""
    return (api_format or API_FORMAT_CHAT_COMPLETIONS).strip().lstrip("/").lower()


def _ctx_api_format(ctx) -> str:
    """读取 ctx 上的 API 格式（与 max_loops 由 ctx 携带同一模式，默认 chat/completions）。"""
    return getattr(ctx, "api_format", API_FORMAT_CHAT_COMPLETIONS) or API_FORMAT_CHAT_COMPLETIONS


def build_api_url(base_url: str, api_format: str = API_FORMAT_CHAT_COMPLETIONS) -> str:
    """根据 API 格式拼接完整端点 URL。

    - chat/completions → 自动补 /chat/completions
    - responses → 自动补 /responses
    已带完整路径时保持原样。
    """
    url = (base_url or "").rstrip("/")
    if _normalize_api_format(api_format) == API_FORMAT_RESPONSES:
        if url.endswith("/responses"):
            return url
        if url.endswith("/chat/completions"):
            url = url[: -len("/chat/completions")].rstrip("/")
        return url + "/responses"

    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/responses"):
        url = url[: -len("/responses")].rstrip("/")
    return url + "/chat/completions"


def _tool_to_responses(openai_tool: dict) -> dict:
    """将 Chat Completions 工具定义转换为 Responses API 扁平结构。

    兼容已扁平的 Responses 工具定义（直接原样返回）。
    """
    if "function" in openai_tool:
        fn = openai_tool["function"]
        return {
            "type": "function",
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {}),
        }
    return openai_tool


def _message_content_to_responses(content):
    """将 Chat 消息 content（str 或 content part 列表）转为 Responses 输入 content。

    纯文本内容优先转成字符串：部分严格网关只接受 `content` 为字符串；
    含图片时保留 content part 数组。
    """
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                parts.append({"type": "input_text", "text": part.get("text", "")})
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if url:
                    # 严格网关要求 image_url 为字符串 URL，而非 {url: ...} 对象
                    parts.append({"type": "input_image", "image_url": url})
    if not parts:
        return ""
    if all(part.get("type") == "input_text" for part in parts):
        return "\n".join(part.get("text", "") for part in parts)
    return parts


def _messages_to_responses_input(messages: list) -> list:
    """将 Chat Completions 的 messages 数组转换为 Responses API 的 input items。

    转换规则：
    - system/user/assistant 文本消息 → message item（assistant 用 output_text）
    - assistant 消息中的 tool_calls → 独立 function_call item
    - tool 消息 → function_call_output item
    """
    items = []
    for msg in messages or []:
        role = msg.get("role", "")
        content = msg.get("content")
        if role in ("system", "developer"):
            parts = _message_content_to_responses(content)
            if parts:
                items.append({"type": "message", "role": role, "content": parts})
        elif role == "user":
            parts = _message_content_to_responses(content)
            if parts:
                items.append({"type": "message", "role": "user", "content": parts})
        elif role == "assistant":
            if content:
                items.append({
                    "type": "message",
                    "role": "assistant",
                    "content": _assistant_content_to_responses(content),
                })
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                items.append({
                    "type": "function_call",
                    "call_id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", ""),
                })
        elif role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id", ""),
                "output": str(content) if content is not None else "",
            })
    return items


def _assistant_content_to_responses(content):
    """将 assistant 消息 content 转为 Responses 的 content。

    纯文本内容优先转成字符串，严格网关更兼容；含其他类型时保留数组。
    """
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append({"type": "output_text", "text": part.get("text", "")})
    if not parts:
        return ""
    if all(part.get("type") == "output_text" for part in parts):
        return "\n".join(part.get("text", "") for part in parts)
    return parts


def _chat_payload_to_responses(payload: dict) -> dict:
    """将 Chat Completions payload 转换为 Responses API 请求体。"""
    body = {"model": payload["model"]}
    if payload.get("messages") is not None:
        body["input"] = _messages_to_responses_input(payload["messages"])
    elif payload.get("input") is not None:
        body["input"] = payload["input"]
    if payload.get("max_tokens"):
        body["max_output_tokens"] = payload["max_tokens"]
    if payload.get("reasoning_effort"):
        body["reasoning"] = {"effort": payload["reasoning_effort"]}
    if payload.get("tools"):
        body["tools"] = [_tool_to_responses(t) for t in payload["tools"]]
    return body


def _parse_responses_choice(resp_json: dict) -> dict:
    """将 Responses API 响应转换为 Chat Completions 风格的 choice dict。

    转换结果包含 message / finish_reason，供现有工具循环透明复用。
    """
    output = resp_json.get("output", [])
    message = {"role": "assistant", "content": None}
    tool_calls = []
    reasoning_parts = []

    for item in output:
        item_type = item.get("type", "")
        if item_type == "message":
            text_parts = []
            for part in item.get("content", []) or []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text_parts.append(part.get("text", ""))
            if text_parts:
                message["content"] = "\n".join(text_parts)
        elif item_type == "reasoning":
            summary = item.get("summary", [])
            if isinstance(summary, list):
                reasoning_parts.extend(
                    part.get("text", "")
                    for part in summary
                    if isinstance(part, dict) and part.get("type") == "summary_text"
                )
            else:
                text = item.get("text") or item.get("content")
                if text:
                    reasoning_parts.append(str(text))
        elif item_type == "function_call":
            call_id = item.get("call_id") or item.get("id") or ""
            tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": item.get("name", ""),
                    "arguments": item.get("arguments", ""),
                },
            })

    if tool_calls:
        message["tool_calls"] = tool_calls
    if reasoning_parts:
        message["reasoning_content"] = "\n".join(reasoning_parts)

    finish_reason = "tool_calls" if tool_calls else "stop"
    return {"message": message, "finish_reason": finish_reason}


def execute_tool(tool_instances, tool_name, arguments):
    for t in tool_instances:
        if t.name == tool_name:
            try:
                result = t._run(**arguments)
                # 如果工具返回 dict，序列化为 JSON 字符串，避免后续切片报错
                if isinstance(result, dict):
                    result = json.dumps(result, ensure_ascii=False)
                return result
            except Exception as e:
                log(f"   ⚠️ 工具 {tool_name} 执行异常: {e}\n{traceback.format_exc()}")
                return f"工具执行错误: {e}"
    return f"未知工具: {tool_name}"


def _compress_history(messages: list, tool_calls_count: int, disable_all: bool = True) -> list:
    """压缩对话历史：移除工具调用对，插入压缩摘要。

    保留 system、user、assistant 文本消息，移除所有 tool_calls + tool_result 对。
    disable_all=True 时提示禁止所有工具；False 时仅提示搜索工具已禁用。
    """
    compressed = []

    for msg in messages:
        role = msg.get("role", "")
        if role == "tool":
            continue
        if role == "assistant" and msg.get("tool_calls"):
            continue
        compressed.append(msg)

    if disable_all:
        summary = (
            f"【系统提示】你共尝试调用工具 {tool_calls_count} 次，"
            "均未获得有效新结果。请勿再使用任何工具，"
            "直接基于你已有的知识和上文已获取的信息完成校对判断。"
        )
    else:
        summary = (
            f"【系统提示】你共尝试调用工具 {tool_calls_count} 次，"
            "均未获得有效新结果。搜索/抓取工具已被禁用，"
            "但你仍可使用文件读写等工具。请基于已有知识和上文信息完成校对。"
        )
    compressed.append({"role": "user", "content": summary})
    return compressed


def _extract_usage(resp_json: dict) -> dict:
    """从 API 响应 json 中提取 usage 信息。

    同时兼容 Chat Completions（prompt_tokens/completion_tokens）与
    Responses API（input_tokens/output_tokens）两种字段命名。

    Returns:
        dict: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        如果响应中无 usage 字段，返回空 dict。
    """
    usage = resp_json.get("usage", {})
    if not isinstance(usage, dict):
        return {}
    return {
        "prompt_tokens": usage.get("prompt_tokens", usage.get("input_tokens", 0)),
        "completion_tokens": usage.get("completion_tokens", usage.get("output_tokens", 0)),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _accumulate_usage(total: dict, usage: dict) -> dict:
    """累加 usage 到 total 中。"""
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        total[key] = total.get(key, 0) + usage.get(key, 0)
    return total


def _is_empty_or_duplicate(result: str, recent_results: list) -> bool:
    """判断工具返回是否为空或与最近结果重复（用于连续空结果检测）。

    注意：SymPy 计算工具始终返回 JSON（含 "success" 字段），
    其开头 ~650 字符为公共 import 块，若按首 500 字符去重会误判。
    因此含有 "success" 字段的 JSON 响应直接视为非空。
    """
    if not result or not result.strip():
        return True
    stripped = result.strip()[:500]

    # SymPy / 工具 JSON 响应始终为非空（开头 500 字符几乎全是 import 块）
    if stripped.startswith('{"success"'):
        return False

    for prev in recent_results[-3:]:
        if prev.strip()[:500] == stripped:
            return True
    empty_markers = [
        "[搜索结果为空", "[搜索无结果", "[网页抓取失败",
        "[未找到", "[网页内容为空", "[识典古籍未收录",
        "[搜韵网未收录", "未知工具:", "[not found]",
        "[error: no text]",
    ]
    for marker in empty_markers:
        if stripped.startswith(marker):
            return True
    return False


def _dump_initial_payload(q_title, system_prompt, md_text, images, openai_tools):
    """将发送给 LLM 的初始请求记录到文件。"""
    lines = []
    lines.append(f"# API 请求记录 — {q_title}\n")
    lines.append(f"## 系统提示词 ({len(system_prompt)} 字符)\n")
    lines.append("```\n" + system_prompt + "\n```\n")
    lines.append(f"\n## 用户文本内容 ({len(md_text)} 字符)\n")
    lines.append("```\n" + md_text[:10000] + ("\n...[截断]" if len(md_text) > 10000 else "") + "\n```\n")
    if images:
        lines.append(f"\n## 图片 ({len(images)} 张)\n")
        for i, img in enumerate(images, 1):
            url = img.get("image_url", {}).get("url", "")
            if url:
                lines.append(f"- 第{i}张: {url[:80]}...\n")
    if openai_tools:
        lines.append(f"\n## 可用工具 ({len(openai_tools)} 个)\n")
        for t in openai_tools:
            lines.append(f"- **{t['function']['name']}**: {t['function']['description'][:120]}\n")
    lines.append("\n---\n\n## LLM 对话记录\n\n")
    return "".join(lines)


# ---- C3: 合并后的统一保存函数 ----

def _save_conversation_log(messages, output_dir, q_title, initial_header, suffix="",
                           reasonings=None):
    """将完整对话记录保存到文件。

    Args:
        suffix: 文件名后缀。"" → _API对话记录.md，"_full" → _API对话记录_full.md。
        reasonings: {assistant 轮次序号: reasoning_content}，逐轮渲染到对话记录。
            reasoning_content 因回传协议不能在 messages 中保留，须并行传入。
    """
    if not output_dir:
        return
    try:
        os.makedirs(output_dir, exist_ok=True)
        filename = f"_API对话记录{suffix}.md"
        log_path = os.path.join(output_dir, filename)
        lines = [initial_header]
        turn = 0
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                continue  # 已在 initial_header 中记录
            elif role == "user":
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            lines.append(f"### 用户输入\n\n```\n{part['text']}\n```\n\n")
                        elif isinstance(part, dict) and part.get("type") == "image_url":
                            lines.append(f"### 用户输入（图片）\n\n[{part.get('image_url', {}).get('url', '')[:80]}...]\n\n")
                else:
                    lines.append(f"### 用户输入\n\n```\n{str(content)}\n```\n\n")
            elif role == "assistant":
                turn += 1
                reasoning = (reasonings or {}).get(turn)
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    lines.append(f"### 第{turn}轮 — LLM 请求工具调用\n\n")
                    if content:
                        lines.append(f"**思考内容:**\n\n```\n{content}\n```\n\n")
                    for tc in tool_calls:
                        tc_name = tc.get("function", {}).get("name", "?")
                        tc_args = tc.get("function", {}).get("arguments", "{}")
                        lines.append(f"- **工具**: `{tc_name}`\n")
                        try:
                            args_obj = json.loads(tc_args)
                            lines.append(f"- **参数**: `{json.dumps(args_obj, ensure_ascii=False)}`\n\n")
                        except Exception:
                            lines.append(f"- **参数**: `{tc_args}`\n\n")
                else:
                    lines.append(f"### 第{turn}轮 — LLM 最终回复\n\n")
                    lines.append(f"```\n{content}\n```\n\n")
                if reasoning:
                    lines.append(f"**推理内容（reasoning_content）:**\n\n"
                                 f"```\n{reasoning}\n```\n\n")
            elif role == "tool":
                lines.append(f"### 工具返回\n\n```\n{str(content)}\n```\n\n")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        log(f"   📝 完整对话记录已保存: {log_path}")
    except Exception as e:
        log(f"   ⚠️ 保存对话记录失败: {e}\n{traceback.format_exc()}")


# ---- C1: 抽取函数 ----

def _post_chat(chat_url, payload, headers,
               api_format: str = API_FORMAT_CHAT_COMPLETIONS):
    """发送一次 API 请求，返回归一化的 (choice_dict, usage_dict)。

    支持 Chat Completions 与 Responses API 两种格式：
    - Chat Completions 直接发送 chat payload，解析 choices[0]
    - Responses API 自动转换请求体，并把响应解析为 chat 风格 choice
    """
    if _normalize_api_format(api_format) == API_FORMAT_RESPONSES:
        resp = requests.post(
            chat_url,
            json=_chat_payload_to_responses(payload),
            headers=headers,
            timeout=TIME_OUT,
        )
        resp.raise_for_status()
        resp_json = resp.json()
        usage = _extract_usage(resp_json)
        choice = _parse_responses_choice(resp_json)
        return choice, usage

    resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
    resp.raise_for_status()
    resp_json = resp.json()
    usage = _extract_usage(resp_json)
    choice = resp_json["choices"][0]
    return choice, usage


def _handle_retry(proof_err, err_msg, retry, consecutive_errors, last_error_type):
    """重试+熔断决策。返回 (should_continue, err_msg, consecutive_errors, last_error_type)。

    调用方根据返回值决定：退避等待后重试 / 立即停止。
    """
    err_type = type(proof_err).__name__
    if err_type == last_error_type:
        consecutive_errors += 1
    else:
        consecutive_errors = 1
        last_error_type = err_type

    # 非可重试错误 → 立即停止
    if not _should_retry(proof_err):
        log(f"   ❌ 不可重试错误 [{err_type}]: {err_msg[:200]}")
        return False, err_msg, consecutive_errors, last_error_type

    # 熔断：连续 3 次同类型可重试错误 → 停止
    if consecutive_errors >= 3:
        log(f"   🔌 熔断触发 [{err_type}]：连续 {consecutive_errors} 次相同错误，停止重试")
        return False, err_msg, consecutive_errors, last_error_type

    # 还有重试次数
    if retry < MAX_RETRY:
        return True, err_msg, consecutive_errors, last_error_type

    return False, err_msg, consecutive_errors, last_error_type


def _build_error_report(ctx, proof_err, err_msg, q_title, consecutive_errors, last_error_type):
    """构造三段 Markdown 错误摘要（不可重试 / 熔断 / 重试耗尽）。"""
    error_context = (
        f"- 模型：`{ctx.model}`\n"
        f"- API 端点：`{ctx.api_url.rstrip('/')}`\n"
        f"- 题目：{q_title}"
    )

    if proof_err is not None and not _should_retry(proof_err):
        # ---- 不可重试错误：给出明确的排查指引 ----
        if isinstance(proof_err, APIAuthError):
            error_summary = (
                f"## 认证失败（HTTP {proof_err.status_code}）\n\n"
                f"API Key 无效或已过期，无法完成 API 调用。\n\n"
                f"### 排查步骤\n"
                f"1. 打开 `subjects/<学科>/.env` 文件\n"
                f"2. 检查 `API_KEY` 是否正确（是否有多余空格、换行）\n"
                f"3. 确认 API Key 是否还有额度\n"
                f"4. 如果使用 DeepSeek：访问 https://platform.deepseek.com/api_keys 查看\n\n"
                f"### 上下文\n{error_context}\n\n"
                f"### 原始错误\n{err_msg}"
            )
        elif isinstance(proof_err, APIBadRequestError):
            # 根据响应体内容给出针对性提示
            resp_hint = ""
            if "image_url" in err_msg and "expected `text`" in err_msg:
                resp_hint = (
                    "\n> ⚠️ 响应体提示：**模型不支持图片输入**（`unknown variant 'image_url', expected 'text'`）。\n"
                    "> `deepseek-reasoner`、`deepseek-v4-pro` 等推理模型是纯文本模型，不能发送图片。\n"
                    "> 程序已自动跳过不兼容模型的图片，如仍出现此错误请检查模型名配置。\n"
                )
            elif "reasoning_effort" in err_msg.lower():
                resp_hint = (
                    "\n> ⚠️ 响应体提示：**模型不支持 `reasoning_effort` 参数**。\n"
                    "> 该参数仅推理模型支持。程序已自动跳过不兼容模型，如仍出现请检查模型名。\n"
                )

            error_summary = (
                f"## 请求格式错误（HTTP 400）\n\n"
                f"API 拒绝了本次请求——请求内容不符合 API 规范。\n\n"
                f"### 常见原因\n"
                f"1. **模型不支持图片**：`deepseek-reasoner`、`deepseek-v4-pro` 等推理模型是纯文本模型，不能发送 `image_url`\n"
                f"2. **模型不支持 `reasoning_effort`**：chat 模型（如 `deepseek-chat`）不支持该参数\n"
                f"3. **模型名称无效**：检查 `.env` 中 `MODEL_NAME` 是否正确\n"
                f"4. **请求体过大**：文本+工具定义超出了模型上下文窗口\n"
                f"{resp_hint}\n"
                f"### 排查步骤\n"
                f"1. 查看上方响应体提示，确认具体拒绝原因\n"
                f"2. 检查 `subjects/<学科>/.env` 中的 `MODEL_NAME`\n"
                f"3. 纯文本模型不要附带图片（程序已自动处理）\n\n"
                f"### 上下文\n{error_context}\n\n"
                f"### 原始错误\n{err_msg}"
            )
        else:
            err_type_name = type(proof_err).__name__
            error_summary = (
                f"## 不可重试错误（{err_type_name}）\n\n"
                f"遇到不可自动恢复的错误，已停止。\n\n"
                f"### 上下文\n{error_context}\n\n"
                f"### 原始错误\n{err_msg}"
            )

    elif consecutive_errors >= 3:
        # ---- 熔断：连续同类型错误 ----
        # 超时类错误额外提示当前超时配置
        timeout_hint = ""
        if last_error_type == "APITimeoutError":
            timeout_hint = (
                f"\n\n> 💡 当前超时配置：连接 {TIME_OUT[0]}s / 读取 {TIME_OUT[1]}s（{TIME_OUT[1] // 60} 分钟）。\n"
                f"> 推理模型单次思考可能超过 10 分钟，如果频繁读取超时，"
                f"可修改 `core/api_client.py` 中的 `TIME_OUT` 增大读取超时。"
            )

        error_summary = (
            f"## API 调用熔断\n\n"
            f"连续 **{consecutive_errors} 次**遇到 `{last_error_type}` 错误，已自动触发熔断保护。\n\n"
            f"### 熔断详情\n"
            f"- 错误类型：`{last_error_type}`\n"
            f"- 连续次数：{consecutive_errors} 次\n"
            f"- 说明：同一错误反复出现，继续重试无意义，已自动停止\n"
            f"{timeout_hint}\n"
            f"### 排查建议\n"
            f"该错误反复出现说明不是临时波动，请根据错误类型排查根因：\n"
            f"- 如果是超时/连接错误 → 检查网络、API 服务状态，或增大超时上限\n"
            f"- 如果是限流（429）→ 降低并发数或等待后重试\n"
            f"- 如果是服务端错误（500/502/503）→ API 服务可能异常，稍后重试\n\n"
            f"### 上下文\n{error_context}\n\n"
            f"### 最近一次错误\n{err_msg}"
        )

    else:
        # ---- 重试耗尽（未触发熔断，如交替不同类型错误） ----
        err_type_name = type(proof_err).__name__ if proof_err else "未知"
        error_summary = (
            f"## API 调用失败（重试耗尽）\n\n"
            f"已尝试 {MAX_RETRY + 1} 次（1 次初始 + {MAX_RETRY} 次重试），均未成功。\n\n"
            f"### 失败详情\n"
            f"- 错误类型：`{err_type_name}`\n"
            f"- 总尝试次数：{MAX_RETRY + 1}\n\n"
            f"### 上下文\n{error_context}\n\n"
            f"### 最后一次错误\n{err_msg}"
        )

    return error_summary


def _build_payload(ctx, state):
    """按 state + ctx 派生本轮请求 payload（不入 state，避免两份清单漂移）。

    重新发送时 payload 总是由最新 messages / openai_tools / reasoning_effort 重建，
    循环内不再对 payload 就地突变。
    """
    payload = {
        "model": ctx.model,
        "messages": state.messages,
        "max_tokens": ctx.max_tokens,
    }
    if state.reasoning_effort:
        payload["reasoning_effort"] = state.reasoning_effort
    if state.openai_tools is not None:
        payload["tools"] = state.openai_tools
    return payload


# ---- C1: _run_tool_loop ----

def _run_tool_loop(ctx, state, tool_instances, chat_url, headers):
    """工具调用循环状态机。返回 LoopResult，4 条退出路径各走各的 stop_reason。

    state 为 ProofreadState 唯一载体：messages/计数器/记录器/累计用量/突变后工具
    全收拢其上；payload 每轮由 ctx + state 派生（_build_payload），无就地突变。
    """
    api_format = _ctx_api_format(ctx)

    def _record_reasoning(msg_dict):
        state.assistant_turn += 1
        reasoning = msg_dict.get("reasoning_content", "")
        if reasoning:
            state.reasonings[state.assistant_turn] = reasoning

    while state.choice.get("finish_reason") == "tool_calls" or state.choice.get("message", {}).get("tool_calls"):
        # 检查中断信号
        if ctx.interrupt_event and ctx.interrupt_event.is_set():
            log("   ⚠️ 收到中断信号，停止工具循环")
            # 中断路径同样补存主对话日志，避免中间过程丢失
            _save_conversation_log(
                state.messages, ctx.output_dir, q_title="", initial_header=state.initial_header,
                reasonings=state.reasonings,
            )
            return LoopResult(
                stop_reason=StopReason.INTERRUPTED,
                messages=state.messages,
                tool_calls_log=state.tool_calls_log,
                usage=state.total_usage,
                reasonings=state.reasonings,
            )

        if state.loop >= ctx.max_loops:
            log(f"   ⚠️ 工具调用超限（{ctx.max_loops}轮），压缩历史 + 去工具...")
            # 保存压缩前的完整日志（含工具调用）
            _save_conversation_log(
                state.messages, ctx.output_dir, q_title="", initial_header=state.initial_header,
                suffix="_full", reasonings=state.reasonings,
            )
            state.messages = _compress_history(state.messages, len(state.tool_calls_log))
            state.openai_tools = None  # 关闭工具调用
            state.choice, usage = _post_chat(chat_url, _build_payload(ctx, state), headers, api_format=api_format)
            _accumulate_usage(state.total_usage, usage)
            reasoning = state.choice.get("message", {}).get("reasoning_content", "")
            content = state.choice["message"]["content"]
            _record_reasoning(state.choice["message"])
            state.messages.append({"role": "assistant", "content": content})
            _save_conversation_log(
                state.messages, ctx.output_dir, q_title="", initial_header=state.initial_header,
                reasonings=state.reasonings,
            )
            return LoopResult(
                content=content,
                reasoning=reasoning,
                messages=state.messages,
                stop_reason=StopReason.MAX_TURNS,
                tool_calls_log=state.tool_calls_log,
                usage=state.total_usage,
                reasonings=state.reasonings,
            )

        # 回传前剔除输出专用字段 reasoning_content（部分端点回传会 400/膨胀）
        _record_reasoning(state.choice["message"])
        state.messages.append({k: v for k, v in state.choice["message"].items()
                               if k != "reasoning_content"})
        # 记录 LLM 返回的工具调用请求
        assistant_text = state.choice["message"].get("content", "")
        if assistant_text:
            log(f"   🤖 LLM 思考: {assistant_text[:150].replace(chr(10), ' ')}")

        # 收集本轮工具名称，判断是否为纯搜索轮次（不占 loop，走独立配额）
        # 兼容 finish_reason="tool_calls" 但 message 无 tool_calls 键的端点
        turn_tool_calls = state.choice["message"].get("tool_calls") or []
        turn_tool_names = {tc["function"]["name"] for tc in turn_tool_calls}
        is_pure_search = turn_tool_names and turn_tool_names.issubset(_SEARCH_TOOLS)

        for tc in turn_tool_calls:
            tool_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(tool_instances, tool_name, args)
            state.tool_calls_log.append({
                "tool": tool_name,
                "args": args,
                "result": result[:2000],
            })
            state.messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result[:8000],
            })
            # 实时输出调用参数 + 返回摘要，方便排查搜索质量
            summary = result[:120].replace('\n', ' ').strip()
            log(f"   🔧 {tool_name}({json.dumps(args, ensure_ascii=False)[:100]}) → {summary}")

            # 连续空结果检测（仅对检索/抓取类工具有效）
            # 搜索工具有独立配额，导航/控制/文件工具不计入
            state.recent_results.append(result)
            if tool_name not in _NAV_CONTROL_TOOLS and tool_name not in _SEARCH_TOOLS:
                if _is_empty_or_duplicate(result, state.recent_results):
                    state.empty_streak += 1
                else:
                    state.empty_streak = 0

            if state.empty_streak >= 3:
                log("   ⚠️ 连续 3 轮空结果，压缩历史 + 移除搜索工具...")
                # 保存压缩前的完整日志（含工具调用），_full 后缀避免被后续覆盖
                _save_conversation_log(
                    state.messages, ctx.output_dir, q_title="", initial_header=state.initial_header,
                    suffix="_full", reasonings=state.reasonings,
                )
                state.messages = _compress_history(state.messages, len(state.tool_calls_log), disable_all=False)
                # 只移除搜索/抓取工具，保留其他工具（read_file、write_file 等）
                state.openai_tools = [t for t in state.openai_tools if t["function"]["name"] not in _SEARCH_TOOLS] if state.openai_tools else None
                state.choice, usage = _post_chat(chat_url, _build_payload(ctx, state), headers, api_format=api_format)
                _accumulate_usage(state.total_usage, usage)
                reasoning = state.choice.get("message", {}).get("reasoning_content", "")
                content = state.choice["message"]["content"]
                _record_reasoning(state.choice["message"])
                state.messages.append({"role": "assistant", "content": content})
                # TOOL_LOOP 路径补存主对话日志（_full 已保存压缩前完整历史）
                _save_conversation_log(
                    state.messages, ctx.output_dir, q_title="", initial_header=state.initial_header,
                    reasonings=state.reasonings,
                )
                return LoopResult(
                    content=content,
                    reasoning=reasoning,
                    messages=state.messages,
                    stop_reason=StopReason.TOOL_LOOP,
                    tool_calls_log=state.tool_calls_log,
                    usage=state.total_usage,
                    reasonings=state.reasonings,
                )

        # 搜索独立配额：纯搜索轮次不占 loop，单独计数
        if is_pure_search:
            state.search_count += 1
            log(f"   🔍 搜索轮次: {state.search_count}/{_MAX_SEARCH}")
            if state.search_count >= _MAX_SEARCH:
                log("   ⚠️ 搜索配额耗尽，移除搜索工具...")
                state.openai_tools = [t for t in state.openai_tools if t["function"]["name"] not in _SEARCH_TOOLS] if state.openai_tools else None
                state.messages.append({"role": "user", "content": "【系统提示】搜索次数已达上限，搜索/抓取工具已被禁用。请继续使用其他工具完成校对。"})
        else:
            state.loop += 1

        state.choice, usage = _post_chat(chat_url, _build_payload(ctx, state), headers, api_format=api_format)
        _accumulate_usage(state.total_usage, usage)

    # while 循环自然结束 → END_TURN
    reasoning = state.choice.get("message", {}).get("reasoning_content", "")
    content = state.choice["message"]["content"]
    _record_reasoning(state.choice.get("message", {}))
    if content:
        state.messages.append({"role": "assistant", "content": content})
    return LoopResult(
        content=content,
        reasoning=reasoning,
        messages=state.messages,
        stop_reason=StopReason.END_TURN,
        tool_calls_log=state.tool_calls_log,
        usage=state.total_usage,
        reasonings=state.reasonings,
    )


# ---- call_api（重构后的编排主函数）----

def call_api(ctx, md_text, images, q_title, system_prompt,
             tools=None):
    """校对 API 调用入口。ctx 为 SessionContext 实例。"""
    err_msg = ""
    proof_err = None
    tool_instances = tools or []
    openai_tools = [tool_to_openai(t) for t in tool_instances] if tool_instances else None
    # 自动检测模型是否支持 reasoning_effort
    reasoning_effort = ctx.reasoning_effort
    if reasoning_effort and not _model_supports_reasoning_effort(ctx.model):
        log(f"   ⚠️ 模型 {ctx.model} 不支持 reasoning_effort 参数，已自动跳过")
        reasoning_effort = None
    # 自动检测模型是否支持图片（纯文本模型发送 image_url 会触发 400）
    if images and not _model_supports_images(ctx.model):
        log(f"   ⚠️ 模型 {ctx.model} 是纯文本模型，不支持图片输入，已自动跳过 {len(images)} 张图片")
        effective_images = []
    else:
        effective_images = images
    # 注入当前校对文本，供 text_nav_tools（locate_paragraph/read_section）使用
    from shared.text_nav_tools import set_current_text as _set_nav_text
    _set_nav_text(md_text)
    # 累计整个 call_api 过程的所有 token 消耗
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    # 连续相同类型错误计数（熔断器）
    consecutive_errors = 0
    last_error_type = None
    api_format = _ctx_api_format(ctx)
    chat_url = build_api_url(ctx.api_url, api_format)

    headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}

    for retry in range(MAX_RETRY + 1):
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": f"编号：{q_title}\n内容：\n{md_text}"},
                    *effective_images,
                ]},
            ]
            # 工具循环状态唯一载体（重试时 openai_tools/total_usage 跨轮共享，与旧行为一致）
            state = ProofreadState(
                messages=messages,
                openai_tools=openai_tools,
                reasoning_effort=reasoning_effort,
                total_usage=total_usage,
            )
            # payload 每轮由 state + ctx 派生
            payload = _build_payload(ctx, state)

            # 记录 payload 大小日志
            _payload_size = len(json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8'))
            log(f"   📤 发送请求 → 模型: {ctx.model}, 系统提示词: {len(system_prompt)}字符, "
                f"文本: {len(md_text)}字符, 图片: {len(effective_images)}张, "
                f"工具: {len(openai_tools) if openai_tools else 0}个, "
                f"payload: {_payload_size // 1024}KB")

            state.initial_header = _dump_initial_payload(q_title, system_prompt, md_text, effective_images, openai_tools)

            # 首次请求
            state.choice, usage = _post_chat(chat_url, payload, headers, api_format=api_format)
            _accumulate_usage(total_usage, usage)

            # 工具循环
            result = _run_tool_loop(ctx, state, tool_instances, chat_url, headers)

            # END_TURN 路径在 _run_tool_loop 内未保存日志，此处补存
            if result.stop_reason == StopReason.END_TURN:
                _save_conversation_log(
                    result.messages, ctx.output_dir, q_title, state.initial_header,
                    reasonings=result.reasonings,
                )

            return result.as_dict()

        except Exception as e:
            proof_err = _classify_error(e)
            err_msg = str(proof_err)

            # 提取 HTTP 响应体（写入 err_msg，确保落入日志文件 _API对话记录.md）
            resp_body = ""
            try:
                if hasattr(e, 'response') and e.response is not None:
                    resp_body = (e.response.text[:1000]
                                 if hasattr(e.response, 'text') else "")
            except Exception:
                pass
            if resp_body:
                err_msg = f"{err_msg}\n\nAPI 响应体：\n{resp_body}"

            # 重试决策
            should_continue, err_msg, consecutive_errors, last_error_type = _handle_retry(
                proof_err, err_msg, retry, consecutive_errors, last_error_type,
            )

            if resp_body and not should_continue:
                log(f"   📋 响应体: {resp_body[:500]}")

            if not should_continue:
                break

            # 退避等待
            backoff_base = getattr(proof_err, 'backoff_base', 2.0)
            delay = _backoff_delay(retry, base=backoff_base)
            # 服务器 Retry-After 建议优先于指数退避（限流时避免加重服务端压力）
            server_retry_after = getattr(proof_err, "retry_after", 0) or 0
            if server_retry_after > 0:
                delay = max(delay, server_retry_after)
            err_type = type(proof_err).__name__
            log(f"   ⚠️ {q_title} 第{retry + 1}次重试（{err_type}，退避 {delay:.0f}s）...")
            time.sleep(delay)

    # ================================================================
    # 所有重试耗尽或不可重试 → 构建详细的错误报告
    # ================================================================
    error_summary = _build_error_report(
        ctx, proof_err, err_msg, q_title, consecutive_errors, last_error_type,
    )

    # 保存错误日志到文件
    _save_conversation_log(
        [], ctx.output_dir, q_title,
        f"# API 请求记录 — {q_title}\n\n"
        f"## 上下文\n- 模型：`{ctx.model}`\n- API 端点：`{ctx.api_url.rstrip('/')}`\n- 题目：{q_title}\n\n"
        f"## 错误报告\n{error_summary}\n",
    )
    return {
        "content": error_summary,
        "tool_calls_log": [],
        "reasoning": "",
        "messages": [],
        "stop_reason": StopReason.ERROR,
        "usage": total_usage,
    }



