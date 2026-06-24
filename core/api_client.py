import json, time
import requests
from core.logging_utils import log

MAX_RETRY = 2
TIME_OUT = 480
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


def call_api(api_url, api_key, model, md_text, images, q_title, system_prompt,
             tools=None, max_loops=20):
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
                "max_tokens": 8192
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
                    log(f"   ⚠️ 工具调用超限（{max_loops}轮），自动重试无工具模式...")
                    payload_no_tools = {**payload, "tools": None, "tool_choice": None}
                    resp = requests.post(chat_url, json=payload_no_tools, headers=headers, timeout=TIME_OUT)
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"], tool_calls_log
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
                        "result": result[:200]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result[:4000]
                    })
                    log(f"   🔧 {tool_name}({json.dumps(args, ensure_ascii=False)[:120]})")
                resp = requests.post(chat_url, json=payload, headers=headers, timeout=TIME_OUT)
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                loop += 1

            return choice["message"]["content"], tool_calls_log
        except Exception as e:
            err_msg = str(e)
            if retry < MAX_RETRY:
                log(f"⚠️ {q_title} 第{retry+1}次重试...")
                time.sleep(2)
    return f"**API调用失败：**\n{err_msg}", []
