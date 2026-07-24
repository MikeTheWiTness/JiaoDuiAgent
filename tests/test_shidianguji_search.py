"""测试识典古籍搜索和节选 —— 两个典型文言文片段。

用法:
    cd d:/JiaoDuiAgent
    python -X utf8 tests/test_shidianguji_search.py          # 完整测试（含网络）
    python -X utf8 tests/test_shidianguji_search.py --offline  # 仅离线
    python -X utf8 tests/test_shidianguji_search.py --file   # 用本地保存的搜索结果
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.chinese_classics_tools import (
    _clean_for_matching,
    _find_best_excerpt_range,
    detect_text_type,
    diff_characters,
    extract_excerpt_from_full,
    search_original_text,
)
from shared.shidianguji_playwright import is_playwright_available

# ── 测试数据 ──────────────────────────────────────────────

WEICOU_EXCERPT = "韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"

DAIZHOU_EXCERPT = "戴胄忠清公直擢为大理少卿上以选人多诈冒资荫敕令"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_search_results")


# ── 辅助函数 ──────────────────────────────────────────────

def indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def print_heading(name: str):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def step1_detect(text: str) -> str:
    """步骤1：文本类型检测"""
    print("\n[步骤1] detect_text_type")
    text_type = detect_text_type(text)
    print(f"  类型: {text_type}")
    if text_type != "classical":
        clean = re.sub(r'\s+', '', text)
        if re.search(r'[一-鿿]{1,4}字[一-鿿]{1,4}', clean):
            if re.search(r'(刺史|司马|长史|司兵|法曹|参军事|太府|通事舍人|太守|县令|尚书|侍郎|御史|大理|少卿)', clean):
                print(f"  (复查: 含传记人名+官职，强制 classical)")
                text_type = "classical"
    return text_type


def step2_search(text_type: str, text: str, use_local: bool = False):
    """步骤2：搜索识典古籍（或用本地缓存）"""
    print("\n[步骤2] search_original_text (识典古籍)")
    if use_local:
        # Try reading saved file
        name = "weicou" if "韦凑" in text else "daizhou"
        path = os.path.join(DATA_DIR, f"{name}_full.txt")
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                original = f.read()
            print(f"  OK: 从本地加载 ({len(original)} 字)")
            return original
        print(f"  FAIL: 本地文件不存在: {path}")
        return None

    if not is_playwright_available():
        print("  SKIP: Playwright 不可用")
        return None

    if text_type == "modern":
        print("  SKIP: 现代文不搜索")
        return None

    original = search_original_text(text_type, text[:20])
    if original is None:
        print("  FAIL: 未找到权威原文")
        return None

    print(f"  OK: 找到原文 ({len(original)} 字)")
    print(f"  开头 200 字:")
    print(indent(original[:200]))
    return original


def step3_excerpt(original, text: str):
    """步骤3：从全文中截取节选"""
    print("\n[步骤3] extract_excerpt_from_full")
    if original is None:
        print("  SKIP: 无原文")
        return None

    excerpt = extract_excerpt_from_full(original, text)
    if excerpt is not None:
        print(f"  OK: 节选成功 ({len(excerpt)} 字)")
        print(f"  内容:")
        print(indent(excerpt[:500]))
        return excerpt

    print("  FAIL: 节选失败")
    n_full = _clean_for_matching(original)
    n_excerpt = _clean_for_matching(text)
    best = _find_best_excerpt_range(n_full, n_excerpt)
    print(f"  诊断: n_full={len(n_full)}字, n_excerpt={len(n_excerpt)}字")
    print(f"        _find_best_excerpt_range → {best}")
    return None


def step4_diff(excerpt, text: str):
    """步骤4：字符 diff"""
    print("\n[步骤4] diff_characters")
    if excerpt is None:
        print("  SKIP: 无节选结果")
        return

    clean_orig = re.sub(r'[#*`\[\]()\s]', '', excerpt)
    clean_given = re.sub(r'[#*`\[\]()\s]', '', text)
    diff_result = diff_characters(clean_orig, clean_given)
    n_diffs = len(diff_result["differences"])

    print(f"  差异数: {n_diffs}")
    if diff_result["identical"]:
        print(f"  RESULT: 字面一致")
    else:
        for i, d in enumerate(diff_result["differences"][:10], 1):
            print(f"  [{d['type']}] pos={d['position']}: '{d.get('original','')}' -> '{d.get('given','')}'")


def run_pipeline(name: str, text: str, use_local: bool = False):
    print_heading(name)
    print(f"  输入 ({len(text)} 字): {text[:120]}")
    tt = step1_detect(text)
    original = step2_search(tt, text, use_local)
    excerpt = step3_excerpt(original, text)
    step4_diff(excerpt, text)


# ── 离线节选逻辑测试 ─────────────────────────────────────

def test_excerpt_logic():
    """不依赖网络 —— 已知原文，纯测节选截取算法。"""
    print_heading("离线测试: 节选算法 (已知正确原文)")

    cases = [
        (
            "韦凑传 - 完全匹配",
            ("韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"
             "徙资州司兵，观察使房昶才之，表于朝，迁扬州法曹。"),
            "韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。",
        ),
        (
            "戴胄传 - 完全匹配",
            ("戴胄忠清公直擢为大理少卿上以选人多诈冒资荫敕令"
             "自首不首者死未几有诈冒事觉者上欲杀之胄奏据法应流"),
            "戴胄忠清公直擢为大理少卿上以选人多诈冒资荫敕令",
        ),
        (
            "韦凑传 - 节选带差异(卒年六十五)",
            ("韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"
             "徙资州司兵，观察使房昶才之，表于朝，迁扬州法曹。"
             "卒，年六十五，赠幽州都督，谥曰文。子见素。"),
            ("韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"
             "卒，年六十五。"),
        ),
        (
            "不相关文本 - 应返回 None",
            "床前明月光，疑是地上霜。举头望明月，低头思故乡。",
            "韦凑字彦宗",
        ),
    ]

    for name, full, excerpt in cases:
        print(f"\n  --- {name} ---")
        print(f"  full ({len(full)}字): {full[:60]}...")
        print(f"  excerpt ({len(excerpt)}字): {excerpt[:60]}...")
        result = extract_excerpt_from_full(full, excerpt)
        if result is not None:
            print(f"  OK: 节选 ({len(result)} 字)")
        else:
            print(f"  RESULT: None (匹配失败)")


# ── 本地文件集成测试 ─────────────────────────────────────

def test_with_local_files():
    """用本地保存的搜索原文 + clean.md 做集成测试。"""
    print_heading("集成测试: 本地搜索结果 + _clean.md")

    for name in ["weicou", "daizhou"]:
        full_path = os.path.join(DATA_DIR, f"{name}_full.txt")
        clean_path = os.path.join(DATA_DIR, f"{name}_clean.md")
        if not os.path.exists(full_path) or not os.path.exists(clean_path):
            print(f"\n  {name}: SKIP (文件不存在)")
            continue

        with open(full_path, encoding='utf-8') as f:
            full = f.read()
        with open(clean_path, encoding='utf-8') as f:
            clean_md = f.read()

        print(f"\n  --- {name} ---")
        print(f"  full={len(full)}字, clean={len(clean_md)}字")
        excerpt = extract_excerpt_from_full(full, clean_md)
        if excerpt:
            print(f"  OK: 节选 {len(excerpt)} 字")
            print(f"  预览: {excerpt[:200]}...")
        else:
            print(f"  FAIL: 节选失败")


# ── 主入口 ─────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true",
                   help="仅运行离线节选测试，不访问网络")
    p.add_argument("--file", action="store_true",
                   help="用本地保存的搜索结果测试")
    args = p.parse_args()

    if args.file:
        test_with_local_files()
    elif args.offline:
        pass  # just test_excerpt_logic below
    else:
        run_pipeline("韦凑传", WEICOU_EXCERPT)
        run_pipeline("戴胄传 (通鉴纪事本末)", DAIZHOU_EXCERPT)

    print()
    test_excerpt_logic()
