import json, time, re
import requests
from core.logging_utils import log

MAX_RETRY = 2
TIME_OUT = 900
MAX_FILE_SIZE = 10 * 1024 * 1024

# ---- StopReason ----

class StopReason:
    """call_api 的显式停止原因，替代隐式 finish_reason 判断。"""
    END_TURN = "end_turn"         # LLM 返回了文本（不含 tool_calls），自然结束
    TOOL_LOOP = "tool_loop"       # 连续 3 轮空/重复结果，触发压缩
    MAX_TURNS = "max_turns"       # max_loops 触顶，触发压缩
    ERROR = "error"               # API 调用异常


def tool_to_openai(tool):
    schema = tool.args_schema.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        }
    }


def execute_tool(tool_instances, tool_name, arguments):
    for t in tool_instances:
        if t.name == tool_name:
            try:
                return t._run(**arguments)
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


def _is_empty_or_duplicate(result: str, recent_results: list) -> bool:
    """判断工具返回是否为空或与最近结果重复（用于连续空结果检测）。"""
    if not result or not result.strip():
        return True
    stripped = result.strip()[:500]
    for prev in recent_results[-3:]:
        if prev.strip()[:500] == stripped:
            return True
    empty_markers = [
        "[搜索结果为空", "[搜索无结果", "[网页抓取失败",
        "[未找到", "[网页内容为空", "[识典古籍未收录",
        "[搜韵网未收录", "未知工具:",
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


def call_api(api_url, api_key, model, md_text, images, q_title, system_prompt,
             tools=None, max_loops=20, max_tokens=32768):
    err_msg = ""
    tool_calls_log = []
    tool_instances = tools or []
    openai_tools = [tool_to_openai(t) for t in tool_instances] if tool_instances else None
    chat_url = api_url.rstrip("/")
    if not chat_url.endswith("/chat/completions"):
        chat_url += "/chat/completions"

    for retry in range(MAX_RETRY + 1):
        tool_calls_log.clear()
        try:
            recent_results = []
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": f"编号：{q_title}\n内容：\n{md_text}"},
                    *images
                ]}
            ]
            payload = {
                "model": model, "messages": messages,
                "temperature": 0.3, "reasoning_effort": "high",
                "max_tokens": max_tokens
            }
            if openai_tools:
                payload["tools"] = openai_tools

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
            resp.raise_for_status()
            choice = resp.json()["choices"][0]

            loop = 0
            while choice.get("finish_reason") == "tool_calls" or choice.get("message", {}).get("tool_calls"):
                if loop >= max_loops:
                    log(f"   ⚠️ 工具调用超限（{max_loops}轮），压缩历史 + 去工具...")
                    messages = _compress_history(messages, len(tool_calls_log))
                    openai_tools = None  # 关闭工具调用
                    payload = {
                        "model": model, "messages": messages,
                        "temperature": 0.3, "reasoning_effort": "high",
                        "max_tokens": max_tokens
                    }
                    resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                    resp.raise_for_status()
                    choice = resp.json()["choices"][0]
                    reasoning = choice.get("message", {}).get("reasoning_content", "")
                    content = choice["message"]["content"]
                    messages.append({"role": "assistant", "content": content})
                    return {
                        "content": content,
                        "tool_calls_log": tool_calls_log,
                        "reasoning": reasoning,
                        "messages": messages,
                        "stop_reason": StopReason.MAX_TURNS,
                    }
                messages.append(choice["message"])
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

                    # 连续空结果检测
                    recent_results.append(result)
                    if _is_empty_or_duplicate(result, recent_results):
                        empty_streak += 1
                    else:
                        empty_streak = 0

                    if empty_streak >= 3:
                        log(f"   ⚠️ 连续 {empty_streak} 轮空结果，压缩历史 + 去工具...")
                        messages = _compress_history(messages, len(tool_calls_log))
                        openai_tools = None
                        payload["tools"] = None
                        payload["messages"] = messages
                        resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                        resp.raise_for_status()
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
                        }
                resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                loop += 1

            reasoning = choice.get("message", {}).get("reasoning_content", "")
            content = choice["message"]["content"]
            if content:
                messages.append({"role": "assistant", "content": content})
            return {
                "content": content,
                "tool_calls_log": tool_calls_log,
                "reasoning": reasoning,
                "messages": messages,
                "stop_reason": StopReason.END_TURN,
            }
        except Exception as e:
            err_msg = str(e)
            if retry < MAX_RETRY:
                log(f"⚠️ {q_title} 第{retry+1}次重试...")
                time.sleep(2)
    return {
        "content": f"**API调用失败：**\n{err_msg}",
        "tool_calls_log": [],
        "reasoning": "",
        "messages": [],
        "stop_reason": StopReason.ERROR,
    }



def call_api_continue(
    api_url: str,
    api_key: str,
    model: str,
    existing_messages: list,
    follow_up_message: str,
    max_tokens: int = 32768,
) -> dict:
    """在已有对话历史上续接一条用户消息，发起单次请求。

    不启动工具循环——仅获取 LLM 的直接回复。用于格式审查重试、LLM 格式修正等场景。

    Args:
        api_url: API 端点
        api_key: API 密钥
        model: 模型名称
        existing_messages: 已有的完整对话历史
        follow_up_message: 追加的用户消息内容
        max_tokens: 最大输出 token 数

    Returns:
        dict: {"content": str, "reasoning": str}
    """
    chat_url = api_url.rstrip("/")
    if not chat_url.endswith("/chat/completions"):
        chat_url += "/chat/completions"

    messages = list(existing_messages)
    messages.append({"role": "user", "content": follow_up_message})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        content = choice["message"]["content"]
        reasoning = choice.get("message", {}).get("reasoning_content", "")
        return {"content": content, "reasoning": reasoning}
    except Exception as e:
        return {"content": f"**API调用失败：**\\n{str(e)}", "reasoning": ""}
