#!/usr/bin/env python
"""端到端测试：模拟 agent 收到前置参考后的完整校对流程。

将搜索 → 节选 → diff 的结果组装为 agent 输入，
通过 call_api 发给大模型，观察 agent 是否：
1. 首轮调用 plan_update 声明计划
2. 逐项执行并更新状态
3. 使用 locate_paragraph / read_section 定位原文
4. 基于前置参考中的差异列表判断
5. 最终输出符合格式的校对结果

用法:
    # 第1题（韦凑传，classical）
    python -X utf8 tests/test_e2e_agent_pipeline.py --q 1

    # 第4题（戴胄传，classical）
    python -X utf8 tests/test_e2e_agent_pipeline.py --q 4

    # 第3题（拉奥孔，modern——不会触発前置搜索）
    python -X utf8 tests/test_e2e_agent_pipeline.py --q 3
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util


def _load_subject_app():
    """加载 SubjectApp，react_mode=True。"""
    subject_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "subjects", "高中语文v3.0",
    )
    spec = importlib.util.spec_from_file_location(
        "_yw", os.path.join(subject_dir, "subject.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    app = mod.SubjectApp(subject_dir)
    app.react_mode = True
    app.tools = app.build_tools()
    return app


def build_test_input(q_dir: str, q_name: str, api_url: str, api_key: str, model: str):
    """为指定题目构造完整 agent 输入。

    返回 (system_prompt, md_content, q_title, has_reference)
    """
    from core.defaults import _strip_search_from_prompt
    from core.logging_utils import log
    from shared.chinese_classics_tools import preprocess_for_proofread

    # ── 1. 加载题目原始 md ──
    target_md = os.path.join(q_dir, f"{q_name}.md")
    if not os.path.exists(target_md):
        raise FileNotFoundError(f"题目文件不存在: {target_md}")

    with open(target_md, encoding="utf-8") as f:
        raw_md = f.read()

    # ── 2. 前置处理：搜索 + 节选 + diff ──
    md_content = preprocess_for_proofread(raw_md, api_url, api_key, model, q_dir=q_dir)

    # ── 3. 构造 agent 系统提示词 ──
    app = _load_subject_app()
    system_prompt = app.get_question_prompt()

    has_reference = "## 前置参考" in md_content

    # 如果有前置参考，移除联网搜索指令 + 移除联网工具
    if has_reference:
        system_prompt = _strip_search_from_prompt(system_prompt)
        tools = [t for t in app.tools if t.name not in ("web_fetch", "web_search")]
        log("   📖 已注入前置参考，移除联网工具")
    else:
        tools = app.tools

    return system_prompt, md_content, q_name, has_reference, tools


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--q", type=int, default=1, help="第几题 (1~4)")
    p.add_argument("--api-url", default="http://10.7.4.132:3000/v1")
    p.add_argument("--api-key", default="sk-local")
    p.add_argument("--model", default="deepseek-v4-flash")
    p.add_argument("--max-loops", type=int, default=15)
    args = p.parse_args()

    q_num = args.q
    api_url = args.api_url
    api_key = args.api_key
    model = args.model

    base = "output/拆题结果/高中语文教研实习生笔试试卷"
    q_dir = os.path.join(base, f"第{q_num}题")
    q_name = f"第{q_num}题"

    print(f"=== 端到端 Agent 测试 ===")
    print(f"题目: {q_dir}")
    print(f"模型: {model}")
    print()

    # ── 构造输入 ──
    system_prompt, md_content, q_title, has_ref, tools = build_test_input(
        q_dir, q_name, api_url, api_key, model
    )

    print(f"系统提示词: {len(system_prompt)} 字符")
    print(f"用户文本:   {len(md_content)} 字符")
    print(f"前置参考:   {'有' if has_ref else '无'}")
    print(f"可用工具:   {[t.name for t in tools]}")
    print(f"最大轮次:   {args.max_loops}")
    print()

    # ── 调用 API ──
    from core.api_client import call_api

    print(">>> 发送请求...")
    result = call_api(
        api_url=api_url,
        api_key=api_key,
        model=model,
        md_text=md_content,
        images=[],
        q_title=q_title,
        system_prompt=system_prompt,
        tools=tools,
        max_loops=args.max_loops,
        max_tokens=32768,
        output_dir=q_dir,
    )

    print()
    print("=== 结果 ===")
    print(f"stop_reason: {result.get('stop_reason', '?')}")
    print(f"tool_calls:  {len(result.get('tool_calls_log', []))} 次")
    print(f"reasoning:   {len(result.get('reasoning', ''))} 字")
    content = result.get("content", "")
    print(f"content:     {len(content)} 字")
    print()
    print("--- LLM 输出 ---")
    print(content[:3000])


if __name__ == "__main__":
    main()
