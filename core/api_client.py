import json, time, re
import requests
from core.logging_utils import log

MAX_RETRY = 2
TIME_OUT = 900
MAX_FILE_SIZE = 10 * 1024 * 1024


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


def _strip_search_instructions(prompt: str) -> str:
    """移除系统提示词中的联网搜索相关指令，用于工具调用超限后的无工具回退重试。

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
                    log(f"   ⚠️ 工具调用超限（{max_loops}轮），清空对话历史重试（无工具）...")
                    # 移除 system prompt 中的联网搜索指令，避免 LLM 继续尝试搜索
                    clean_system = _strip_search_instructions(system_prompt)
                    clean_messages = [
                        {"role": "system", "content": clean_system},
                        {"role": "user", "content": [
                            {"type": "text", "text": f"编号：{q_title}\n内容：\n{md_text}"},
                            *images
                        ]}
                    ]
                    clean_payload = {
                        "model": model, "messages": clean_messages,
                        "temperature": 0.3, "reasoning_effort": "high",
                        "max_tokens": max_tokens
                    }
                    resp = requests.post(chat_url, json=clean_payload, headers=headers, timeout=TIME_OUT)
                    resp.raise_for_status()
                    clean_choice = resp.json()["choices"][0]
                    reasoning = clean_choice.get("message", {}).get("reasoning_content", "")
                    return clean_choice["message"]["content"], tool_calls_log, reasoning
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
                resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                loop += 1

            reasoning = choice.get("message", {}).get("reasoning_content", "")
            return choice["message"]["content"], tool_calls_log, reasoning
        except Exception as e:
            err_msg = str(e)
            if retry < MAX_RETRY:
                log(f"⚠️ {q_title} 第{retry+1}次重试...")
                time.sleep(2)
    return f"**API调用失败：**\n{err_msg}", [], ""
