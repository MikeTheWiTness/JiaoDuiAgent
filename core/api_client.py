import json, time, re, os
from pathlib import Path
import requests
from core.logging_utils import log

MAX_RETRY = 2
# 超时设置：(连接超时, 读取超时)
# - 连接超时 30s：建立 TCP/TLS 连接的上限，绰绰有余
# - 读取超时 1800s（30 分钟）：推理模型（如 deepseek-v4-pro + reasoning_effort=high）
#   单次思考可能超过 10 分钟，加上工具调用循环，30 分钟是合理上限
TIME_OUT = (30, 1800)
MAX_FILE_SIZE = 10 * 1024 * 1024

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
                return f"工具执行错误: {e}"
    return f"未知工具: {tool_name}"


def _compress_history(messages: list, tool_calls_count: int) -> list:
    """压缩对话历史：移除工具调用对，插入压缩摘要。

    保留 system、user、assistant 文本消息，移除所有 tool_calls + tool_result 对。
    """
    compressed = []

    for msg in messages:
        role = msg.get("role", "")
        if role == "tool":
            continue
        if role == "assistant" and msg.get("tool_calls"):
            continue
        compressed.append(msg)

    summary = (
        f"【系统提示】你共尝试调用工具 {tool_calls_count} 次，"
        "均未获得有效新结果。请勿再使用任何工具，"
        "直接基于你已有的知识和上文已获取的信息完成校对判断。"
    )
    compressed.append({"role": "user", "content": summary})
    return compressed


def _extract_usage(resp_json: dict) -> dict:
    """从 API 响应 json 中提取 usage 信息。

    Returns:
        dict: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        如果响应中无 usage 字段，返回空 dict。
    """
    usage = resp_json.get("usage", {})
    if not isinstance(usage, dict):
        return {}
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
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


def _strip_search_instructions(prompt: str) -> str:
    """移除系统提示词中的联网搜索相关指令。
    （保留用于 _format_retry 场景，call_api 主流程使用压缩历史替代清空重来）

    清理目标：
    - "## 可用的联网搜索工具" 整段（工具介绍 + 使用规则）
    - 残留的 web_search / web_fetch 提及
    然后追加明确指令，禁止 LLM 继续尝试搜索。
    """
    # 移除工具介绍段落（"## 可用的联网搜索工具" 到下一个 "## " 标题前）
    cleaned = re.sub(
        r'\n*## 可用的联网搜索工具\n.*?(?=\n## )',
        '',
        prompt,
        flags=re.DOTALL,
    )
    # 清理可能残留的多余空行
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    # 追加重试说明
    cleaned = cleaned.rstrip() + (
        "\n\n**注意：本次校对不提供联网搜索功能，"
        "请直接根据你的知识和上文已搜索到的结果进行校对判断，不要再尝试调用搜索工具。**"
    )
    return cleaned


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


def _save_conversation_log(messages, output_dir, q_title, initial_header):
    """将完整对话记录保存到文件。"""
    if not output_dir:
        return
    try:
        os.makedirs(output_dir, exist_ok=True)
        log_path = os.path.join(output_dir, "_API对话记录.md")
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
                            lines.append(f"### 用户输入\n\n```\n{part['text'][:5000]}\n```\n\n")
                        elif isinstance(part, dict) and part.get("type") == "image_url":
                            lines.append(f"### 用户输入（图片）\n\n[{part.get('image_url', {}).get('url', '')[:80]}...]\n\n")
                else:
                    lines.append(f"### 用户输入\n\n```\n{str(content)[:5000]}\n```\n\n")
            elif role == "assistant":
                turn += 1
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    lines.append(f"### 第{turn}轮 — LLM 请求工具调用\n\n")
                    if content:
                        lines.append(f"**思考内容:**\n\n```\n{content[:2000]}\n```\n\n")
                    for tc in tool_calls:
                        tc_name = tc.get("function", {}).get("name", "?")
                        tc_args = tc.get("function", {}).get("arguments", "{}")
                        lines.append(f"- **工具**: `{tc_name}`\n")
                        try:
                            args_obj = json.loads(tc_args)
                            lines.append(f"- **参数**: `{json.dumps(args_obj, ensure_ascii=False)[:300]}`\n\n")
                        except Exception:
                            lines.append(f"- **参数**: `{tc_args[:300]}`\n\n")
                else:
                    lines.append(f"### 第{turn}轮 — LLM 最终回复\n\n")
                    lines.append(f"```\n{content[:10000]}{'...[截断]' if len(str(content)) > 10000 else ''}\n```\n\n")
            elif role == "tool":
                lines.append(f"### 工具返回\n\n```\n{str(content)[:5000]}\n```\n\n")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        log(f"   📝 完整对话记录已保存: {log_path}")
    except Exception as e:
        log(f"   ⚠️ 保存对话记录失败: {e}")


def _save_conversation_log_full(messages, output_dir, q_title, initial_header):
    """与 _save_conversation_log 相同，但保存到 _API对话记录_full.md。

    用于在压缩历史前保留完整的工具调用记录，便于排查问题。
    """
    if not output_dir:
        return
    try:
        os.makedirs(output_dir, exist_ok=True)
        log_path = os.path.join(output_dir, "_API对话记录_full.md")
        lines = [initial_header]
        turn = 0
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                continue
            elif role == "user":
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            lines.append(f"### 用户输入\n\n```\n{part['text'][:5000]}\n```\n\n")
                        elif isinstance(part, dict) and part.get("type") == "image_url":
                            lines.append(f"### 用户输入（图片）\n\n[{part.get('image_url', {}).get('url', '')[:80]}...]\n\n")
                else:
                    lines.append(f"### 用户输入\n\n```\n{str(content)[:5000]}\n```\n\n")
            elif role == "assistant":
                turn += 1
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    lines.append(f"### 第{turn}轮 — LLM 请求工具调用\n\n")
                    if content:
                        lines.append(f"**思考内容:**\n\n```\n{content[:2000]}\n```\n\n")
                    for tc in tool_calls:
                        tc_name = tc.get("function", {}).get("name", "?")
                        tc_args = tc.get("function", {}).get("arguments", "{}")
                        lines.append(f"- **工具**: `{tc_name}`\n")
                        try:
                            args_obj = json.loads(tc_args)
                            lines.append(f"- **参数**: `{json.dumps(args_obj, ensure_ascii=False)[:300]}`\n\n")
                        except Exception:
                            lines.append(f"- **参数**: `{tc_args[:300]}`\n\n")
                else:
                    lines.append(f"### 第{turn}轮 — LLM 最终回复\n\n")
                    lines.append(f"```\n{content[:10000]}{'...[截断]' if len(str(content)) > 10000 else ''}\n```\n\n")
            elif role == "tool":
                lines.append(f"### 工具返回\n\n```\n{str(content)[:5000]}\n```\n\n")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("".join(lines))
    except Exception:
        pass  # 完整的日志保存失败不应影响主流程


def call_api(ctx, md_text, images, q_title, system_prompt,
             tools=None):
    """校对 API 调用入口。ctx 为 SessionContext 实例。"""
    err_msg = ""
    proof_err = None
    tool_calls_log = []
    tool_instances = tools or []
    openai_tools = [tool_to_openai(t) for t in tool_instances] if tool_instances else None
    # 自动检测模型是否支持 reasoning_effort
    reasoning_effort = ctx.reasoning_effort
    if reasoning_effort and not _model_supports_reasoning_effort(ctx.model):
        log(f"   ⚠️ 模型 {ctx.model} 不支持 reasoning_effort 参数，已自动跳过")
        reasoning_effort = None
    # 自动检测模型是否支持图片（纯文本模型发送 image_url 会触发 400）
    effective_images = images
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
    chat_url = ctx.api_url.rstrip("/")
    if not chat_url.endswith("/chat/completions"):
        chat_url += "/chat/completions"

    for retry in range(MAX_RETRY + 1):
        tool_calls_log.clear()
        try:
            recent_results = []
            empty_streak = 0
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": f"编号：{q_title}\n内容：\n{md_text}"},
                    *effective_images
                ]}
            ]
            payload = {
                "model": ctx.model, "messages": messages,
                "temperature": 0.3,
                "max_tokens": ctx.max_tokens
            }
            if reasoning_effort:
                payload["reasoning_effort"] = reasoning_effort
            if openai_tools:
                payload["tools"] = openai_tools

            # 记录 payload 大小日志
            _payload_size = len(json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8'))
            log(f"   📤 发送请求 → 模型: {ctx.model}, 系统提示词: {len(system_prompt)}字符, "
                f"文本: {len(md_text)}字符, 图片: {len(images)}张, "
                f"工具: {len(openai_tools) if openai_tools else 0}个, "
                f"payload: {_payload_size//1024}KB")

            initial_header = _dump_initial_payload(q_title, system_prompt, md_text, images, openai_tools)

            headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}
            resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
            resp.raise_for_status()
            _accumulate_usage(total_usage, _extract_usage(resp.json()))
            choice = resp.json()["choices"][0]

            loop = 0
            while choice.get("finish_reason") == "tool_calls" or choice.get("message", {}).get("tool_calls"):
                # 检查中断信号
                if ctx.interrupt_event and ctx.interrupt_event.is_set():
                    log("   ⚠️ 收到中断信号，停止工具循环")
                    return {
                        "content": "",
                        "tool_calls_log": tool_calls_log,
                        "reasoning": "",
                        "messages": messages,
                        "stop_reason": "interrupted",
                        "usage": total_usage,
                    }
                if loop >= ctx.max_loops:
                    log(f"   ⚠️ 工具调用超限（{ctx.max_loops}轮），压缩历史 + 去工具...")
                    # 保存压缩前的完整日志（含工具调用）
                    _save_conversation_log_full(
                        messages, ctx.output_dir, q_title, initial_header)
                    messages = _compress_history(messages, len(tool_calls_log))
                    openai_tools = None  # 关闭工具调用
                    payload = {
                        "model": ctx.model, "messages": messages,
                        "temperature": 0.3,
                        "max_tokens": ctx.max_tokens
                    }
                    if reasoning_effort:
                        payload["reasoning_effort"] = reasoning_effort
                    resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                    resp.raise_for_status()
                    _accumulate_usage(total_usage, _extract_usage(resp.json()))
                    choice = resp.json()["choices"][0]
                    reasoning = choice.get("message", {}).get("reasoning_content", "")
                    content = choice["message"]["content"]
                    messages.append({"role": "assistant", "content": content})
                    _save_conversation_log(messages, ctx.output_dir, q_title, initial_header)
                    return {
                        "content": content,
                        "tool_calls_log": tool_calls_log,
                        "reasoning": reasoning,
                        "messages": messages,
                        "stop_reason": StopReason.MAX_TURNS,
                        "usage": total_usage,
                    }
                messages.append(choice["message"])
                # 记录 LLM 返回的工具调用请求
                assistant_text = choice["message"].get("content", "")
                if assistant_text:
                    log(f"   🤖 LLM 思考: {assistant_text[:150].replace(chr(10), ' ')}")
                for tc in choice["message"]["tool_calls"]:
                    tool_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    result = execute_tool(tool_instances, tool_name, args)
                    tool_calls_log.append({
                        "tool": tool_name,
                        "args": args,
                        "result": result[:2000]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result[:8000]
                    })
                    # 实时输出调用参数 + 返回摘要，方便排查搜索质量
                    summary = result[:120].replace('\n', ' ').strip()
                    log(f"   🔧 {tool_name}({json.dumps(args, ensure_ascii=False)[:100]}) → {summary}")

                    # 连续空结果检测（仅对检索/抓取类工具有效）
                    # read_file / write_file / plan_update / locate_paragraph /
                    # read_section 属于流程控制 / 文本 / 文件工具，不应计入
                    _NAV_CONTROL_TOOLS = {
                        "plan_update", "locate_paragraph", "read_section",
                        "read_file", "write_file", "independent_solve",
                    }
                    recent_results.append(result)
                    if tool_name not in _NAV_CONTROL_TOOLS:
                        if _is_empty_or_duplicate(result, recent_results):
                            empty_streak += 1
                        else:
                            empty_streak = 0

                    if empty_streak >= 3:
                        log(f"   ⚠️ 连续 {empty_streak} 轮空结果，压缩历史 + 去工具...")
                        # 保存压缩前的完整日志（含工具调用），_full 后缀避免被后续覆盖
                        _save_conversation_log_full(
                            messages, ctx.output_dir, q_title, initial_header)
                        messages = _compress_history(messages, len(tool_calls_log))
                        openai_tools = None
                        payload["tools"] = None
                        payload["messages"] = messages
                        resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                        resp.raise_for_status()
                        _accumulate_usage(total_usage, _extract_usage(resp.json()))
                        choice = resp.json()["choices"][0]
                        reasoning = choice.get("message", {}).get("reasoning_content", "")
                        content = choice["message"]["content"]
                        messages.append({"role": "assistant", "content": content})
                        return {
                            "content": content,
                            "tool_calls_log": tool_calls_log,
                            "reasoning": reasoning,
                            "messages": messages,
                            "stop_reason": StopReason.TOOL_LOOP,
                            "usage": total_usage,
                        }
                resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                resp.raise_for_status()
                _accumulate_usage(total_usage, _extract_usage(resp.json()))
                choice = resp.json()["choices"][0]
                loop += 1

            reasoning = choice.get("message", {}).get("reasoning_content", "")
            content = choice["message"]["content"]
            if content:
                messages.append({"role": "assistant", "content": content})
            _save_conversation_log(messages, ctx.output_dir, q_title, initial_header)
            return {
                "content": content,
                "tool_calls_log": tool_calls_log,
                "reasoning": reasoning,
                "messages": messages,
                "stop_reason": StopReason.END_TURN,
                "usage": total_usage,
            }
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

            # 熔断器：连续同类型错误计数
            err_type = type(proof_err).__name__
            if err_type == last_error_type:
                consecutive_errors += 1
            else:
                consecutive_errors = 1
                last_error_type = err_type

            # 非可重试错误 → 立即停止
            if not _should_retry(proof_err):
                log(f"   ❌ 不可重试错误 [{err_type}]: {err_msg[:200]}")
                if resp_body:
                    log(f"   📋 响应体: {resp_body[:500]}")
                break

            # 熔断：连续 3 次同类型可重试错误 → 停止
            if consecutive_errors >= 3:
                log(f"   🔌 熔断触发 [{err_type}]：连续 {consecutive_errors} 次相同错误，停止重试")
                if resp_body:
                    log(f"   📋 响应体: {resp_body[:500]}")
                break

            if retry < MAX_RETRY:
                # 根据错误类型计算退避延迟
                backoff_base = getattr(proof_err, 'backoff_base', 2.0)
                delay = _backoff_delay(retry, base=backoff_base)
                log(f"   ⚠️ {q_title} 第{retry+1}次重试（{err_type}，退避 {delay:.0f}s）...")
                time.sleep(delay)
    # ================================================================
    # 所有重试耗尽或不可重试 → 构建详细的错误报告
    # ================================================================
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
                f"\n\n> 💡 当前超时配置：连接 {TIME_OUT[0]}s / 读取 {TIME_OUT[1]}s（{TIME_OUT[1]//60} 分钟）。\n"
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

    # 保存错误日志到文件
    _save_conversation_log(
        [], ctx.output_dir, q_title,
        f"# API 请求记录 — {q_title}\n\n"
        f"## 上下文\n{error_context}\n\n"
        f"## 错误报告\n{error_summary}\n"
    )
    return {
        "content": error_summary,
        "tool_calls_log": [],
        "reasoning": "",
        "messages": [],
        "stop_reason": StopReason.ERROR,
        "usage": total_usage,
    }



def call_api_continue(
    ctx,
    existing_messages: list,
    follow_up_message: str,
) -> dict:
    """在已有对话历史上续接一条用户消息，发起单次请求。

    不启动工具循环——仅获取 LLM 的直接回复。用于格式审查重试、LLM 格式修正等场景。
    """
    chat_url = ctx.api_url.rstrip("/")
    if not chat_url.endswith("/chat/completions"):
        chat_url += "/chat/completions"

    messages = list(existing_messages)
    messages.append({"role": "user", "content": follow_up_message})

    payload = {
        "model": ctx.model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": ctx.max_tokens,
    }

    headers = {"Authorization": f"Bearer {ctx.api_key}", "Content-Type": "application/json"}

    try:
        log(f"   📤 [格式修正] 发送请求: {follow_up_message[:120].replace(chr(10), ' ')}...")
        resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        content = choice["message"]["content"]
        reasoning = choice.get("message", {}).get("reasoning_content", "")
        log(f"   📥 [格式修正] LLM 返回: {content[:120].replace(chr(10), ' ')}...")
        return {"content": content, "reasoning": reasoning}
    except Exception as e:
        proof_err = _classify_error(e)
        err_type = type(proof_err).__name__
        err_msg = str(proof_err)

        # 提取响应体
        resp_body = ""
        try:
            if hasattr(e, 'response') and e.response is not None:
                resp_body = (e.response.text[:500]
                             if hasattr(e.response, 'text') else "")
        except Exception:
            pass

        log(f"   ❌ [格式修正] {err_type}: {err_msg[:200]}")
        if resp_body:
            log(f"   📋 [格式修正] 响应体: {resp_body}")

        # 构建详细错误信息
        detail = f"[格式修正] {err_type}: {err_msg}"
        if resp_body:
            detail += f"\n响应体: {resp_body}"
        return {"content": f"**格式修正 API 调用失败：**\n{detail}", "reasoning": ""}
