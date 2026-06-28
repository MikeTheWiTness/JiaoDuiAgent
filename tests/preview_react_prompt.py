#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""预览 ReAct 校对发送给 LLM 的完整提示词（不调用 LLM）。

用 tests/_search_results 下已保存的预检索全文（*_full.txt）替代联网搜索，
走真实代码路径 preprocess_for_proofread → 节选 → diff → 注入「前置参考」，
再拼出 system + user 消息，落盘供人工审阅。

用法:
    python -X utf8 tests/preview_react_prompt.py            # 默认第1、4题
    python -X utf8 tests/preview_react_prompt.py --q 4      # 只看第4题（戴胄）
    python -X utf8 tests/preview_react_prompt.py --q 1      # 只看第1题（韦凑）
"""
import sys
import os
import argparse
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_search_results")
PAPER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "拆题结果", "高中语文教研实习生笔试试卷",
)

# 题号 → (搜索结果名, 题目标签)
Q_MAP = {
    1: ("weicou", "韦凑传"),
    4: ("daizhou", "戴胄传"),
}


def _load_subject_app():
    """加载 SubjectApp，react_mode=True（与真实校对一致）。"""
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


def build_prompt_preview(q_num: int):
    """返回 (system_prompt, user_text, meta_dict)。不调用 LLM、不联网。"""
    import shared.chinese_classics_tools as cc

    name, label = Q_MAP[q_num]
    q_dir = os.path.join(PAPER_DIR, f"第{q_num}题")
    q_name = f"第{q_num}题"
    target_md = os.path.join(q_dir, f"{q_name}.md")
    with open(target_md, "r", encoding="utf-8") as f:
        raw_md = f.read()

    # 读已保存的预检索全文，monkeypatch 掉联网搜索
    full_path = os.path.join(DATA_DIR, f"{name}_full.txt")
    with open(full_path, "r", encoding="utf-8") as f:
        saved_full = f.read()

    real_search = cc.search_original_text
    cc.search_original_text = lambda text_type, sample_text: saved_full
    try:
        md_content = cc.preprocess_for_proofread(raw_md, q_dir=q_dir)
    finally:
        cc.search_original_text = real_search

    # system 提示词（与 default_proofread_one / build_test_input 一致）
    app = _load_subject_app()
    system_prompt = app.get_question_prompt()
    has_ref = "## 前置参考" in md_content
    if has_ref:
        from core.defaults import _strip_search_from_prompt
        system_prompt = _strip_search_from_prompt(system_prompt)
        tools = [t for t in app.tools if t.name not in ("web_fetch", "web_search")]
    else:
        tools = app.tools

    # user 消息（与 call_api 的拼装一致：编号 + 内容）
    user_text = f"编号：{q_name}\n内容：\n{md_content}"

    # 统计差异条目数（按 build_reference_section 输出的编号列表行计数）
    import re as _re
    n_diff = len(_re.findall(r'^\d+\. 第\d+位', md_content, flags=_re.MULTILINE))

    meta = {
        "q_num": q_num,
        "label": label,
        "text_type": "classical" if has_ref else "modern/未触发",
        "has_reference": has_ref,
        "n_diffs": n_diff,
        "tools": [t.name for t in tools],
        "system_len": len(system_prompt),
        "user_len": len(user_text),
        "md_raw_len": len(raw_md),
        "md_injected_len": len(md_content),
    }
    return system_prompt, user_text, meta


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--q", type=int, default=0, help="题号 (1 或 4)；0=两个都生成")
    args = p.parse_args()

    qs = [args.q] if args.q else [1, 4]
    for q in qs:
        if q not in Q_MAP:
            print(f"⚠️ 第{q}题不在预览范围（仅支持 1=韦凑, 4=戴胄）")
            continue

        system_prompt, user_text, meta = build_prompt_preview(q)

        out_path = os.path.join(DATA_DIR, f"_prompt_preview_第{q}题.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# ReAct 校对提示词预览 — 第{q}题（{meta['label']}）\n\n")
            f.write("> 本文件为发送给 LLM 前的完整提示词预览，未实际调用 LLM。\n")
            f.write("> 预检索全文取自本地 _search_results/*_full.txt，diff 与注入走真实代码路径。\n\n")
            f.write("## 元信息\n\n")
            f.write(f"- 文本类型: `{meta['text_type']}`\n")
            f.write(f"- 前置参考: {'有' if meta['has_reference'] else '无'}\n")
            f.write(f"- 字面差异条目数: {meta['n_diffs']}\n")
            f.write(f"- 可用工具: {meta['tools']}\n")
            f.write(f"- system 提示词长度: {meta['system_len']} 字符\n")
            f.write(f"- user 消息长度: {meta['user_len']} 字符\n")
            f.write(f"- 题目原文长度: {meta['md_raw_len']} 字符 → 注入后: {meta['md_injected_len']} 字符\n\n")
            f.write("---\n\n")
            f.write("## ===== 系统提示词 (system) =====\n\n")
            f.write(system_prompt)
            f.write("\n\n---\n\n")
            f.write("## ===== 用户消息 (user) =====\n\n")
            f.write("```\n")
            f.write(user_text)
            f.write("\n```\n")

        print(f"=== 第{q}题（{meta['label']}）===")
        print(f"  前置参考: {'有' if meta['has_reference'] else '无'} | 差异条目: {meta['n_diffs']} | 工具: {meta['tools']}")
        print(f"  system: {meta['system_len']}字符 | user: {meta['user_len']}字符")
        print(f"  已写入: {out_path}")
        print()


if __name__ == "__main__":
    main()
