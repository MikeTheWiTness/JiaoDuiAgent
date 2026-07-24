#!/usr/bin/env python
"""诊断：同一 diff 算法，为何测试得 ~7 条差异，真实管线得 111 条。

对比两条路径（都用本地保存的 weicou_full.txt，不联网）：
  路径A — test_shidianguji_search.run_pipeline 用的 25 字手摘开头
  路径B — preprocess_for_proofread 用的整道题 clean.md
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.chinese_classics_tools import diff_characters, extract_excerpt_from_full

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_search_results")
PAPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output", "拆题结果", "高中语文教研实习生笔试试卷",
)

with open(os.path.join(DATA, "weicou_full.txt"), encoding="utf-8") as f:
    full = f.read()
with open(os.path.join(PAPER, "第1题", "第1题_clean.md"), encoding="utf-8") as f:
    clean_md = f.read()

WEICOU_EXCERPT = "韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"


def diff_path(name, given_text):
    excerpt = extract_excerpt_from_full(full, given_text)
    if not excerpt:
        print(f"\n[{name}] 节选失败（返回 None）")
        return
    clean_orig = re.sub(r'[#*`\[\]()\s]', '', excerpt)
    clean_given = re.sub(r'[#*`\[\]()\s]', '', given_text)
    d = diff_characters(clean_orig, clean_given)
    print(f"\n[{name}]")
    print(f"  given 输入长度: {len(clean_given)} 汉字 | 节选原文长度: {len(clean_orig)} 汉字")
    print(f"  节选原文开头: {clean_orig[:40]}...")
    print(f"  差异条数: {len(d['differences'])}")
    for i, x in enumerate(d['differences'][:12], 1):
        print(f"    {i}. 「{x.get('original','')}」→「{x.get('given','')}」 ({x.get('type')})")
    if len(d['differences']) > 12:
        print(f"    ... 共 {len(d['differences'])} 条")


diff_path("路径A（测试 run_pipeline: 25字开头 WEICOU_EXCERPT）", WEICOU_EXCERPT)
diff_path("路径B（真实管线 preprocess_for_proofread: 整道题 clean.md）", clean_md)

# 路径C：新管线 —— extract_body_segment 切正文段 + _clean_for_matching 两侧纯汉字
from shared.chinese_classics_tools import _clean_for_matching, extract_body_segment

with open(os.path.join(PAPER, "第1题", "第1题.md"), encoding="utf-8") as f:
    raw1 = f.read()
body = extract_body_segment(raw1)
print(f"\n[路径C（新管线: extract_body_segment 切正文段）]")
if not body:
    print("  extract_body_segment 返回 None")
else:
    excerpt = extract_excerpt_from_full(full, body)
    if not excerpt:
        print("  节选失败（返回 None）")
    else:
        co = _clean_for_matching(excerpt)
        cg = _clean_for_matching(body)
        d = diff_characters(co, cg)
        print(f"  body 长度: {len(cg)} 汉字 | 节选原文长度: {len(co)} 汉字")
        print(f"  节选原文开头: {co[:40]}...")
        print(f"  差异条数: {len(d['differences'])}")
        for i, x in enumerate(d['differences'][:12], 1):
            print(f"    {i}. 「{x.get('original','')}」→「{x.get('given','')}」 ({x.get('type')})")
        if len(d['differences']) > 12:
            print(f"    ... 共 {len(d['differences'])} 条")
