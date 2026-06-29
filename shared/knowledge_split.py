"""知识讲义智能切割管线。

管线：
  步骤 1（Python）：全文结构编目 → 列出所有结构信号（标题/编号/段头/嵌入题目标记）
  步骤 2（LLM）：基于结构清单 + 原文头尾，决定切分方案 + 类型标注
  步骤 3（Python）：校验 → bash 逆序插入标签 → 复核

中间产物（全部落盘到 output/中间产物/{文档名}/）：
  - _knowledge_catalog.json       步骤 1 结构编目清单
  - _knowledge_llm_input.txt      步骤 2 LLM 输入（结构清单 + 段头尾）
  - _knowledge_llm_raw.txt        步骤 2 LLM 原始返回
  - _knowledge_llm_parsed.json    步骤 2 解析后的切分方案
  - _knowledge_anchors.json       步骤 3 锚点校验结果
  - _knowledge_tagged.md          步骤 3 插入标签后的全文
  - _knowledge_verify.json        步骤 3 复核结果
"""

import json
import os
import re
import traceback
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_utils import log


# ============================================================================
# 步骤 1：全文结构编目（纯 Python，通用——不针对任何特定讲义格式）
# ============================================================================

# 标题行（## 到 ######）
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)')

# （N）编号的条目（如"（1）《庄子》"浑沌之死""）
_ITEM_NUMBER_RE = re.compile(r'^（(\d+)）(.+)')

# 知识点固定段头
_KNOWLEDGE_SIGNALS = [
    "【寓意】", "【适用角度】", "【事例句运用】", "【标签化引用】",
    "【文段示例】", "【文段展示】", "【详解】", "【参考例文】",
    "【出题意图】", "❎【误用示例】",
]

# 题目相关标记
_EXAM_SIGNALS = [
    "**审题：**", "**立意：**", "【详解】",
]

# 嵌入题目/补充题的引导语
_EXAM_MARKER_RE = re.compile(
    r'^(补充题[一二三四五六七八九十]+|典型例题[一二三四五六七八九十]+|'
    r'即时练|【出题意图】)'
)

# 方法/步骤标记
_METHOD_SIGNAL_RE = re.compile(r'^(第[一二三四五六七八九十\d]+步|方法[一二三四五六七八九十\d]+)')

# 分班/管理标记（不需要校对的内容）
_SKIP_SIGNALS = [
    "分班型：", "目标双一流班", "目标清北班", "复习25暑讲过的",
    "【原版】", "【新增素材版】", "[运用素材大招：]", "[25暑第五讲：]",
    "[素材组合技巧：]", "解答：  【参考示例】", "解答：  【参考答案】",
]

# 万用主题 / 主题变体
_THEME_SIGNAL_RE = re.compile(r'^\*\*主题[一二三四五六七八九十\d]+：')


def _scan_structure(content: str) -> dict:
    """全文结构编目：列出所有可识别的结构信号，不做切割、不做置信度评判。

    返回一份"文档目录清单"，每条记录包含：
      - line: 行号（0-based）
      - type: 信号类型（heading / item_number / knowledge_signal /
              exam_marker / method_step / theme_variant / skip_signal / unknown）
      - level: 标题层级（仅 heading 类型有效，1-6）
      - text: 该行的 stripped 文本

    Returns:
        {
          "catalog": [ {...}, {...}, ... ],
          "total_lines": int,
          "total_chars": int,
        }
    """
    lines = content.split("\n")
    catalog = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        entry = {"id": f"L{i:04d}", "line": i, "text": stripped}

        # 1. 标题行
        m = _HEADING_RE.match(stripped)
        if m:
            entry["type"] = "heading"
            entry["level"] = len(m.group(1))
            catalog.append(entry)
            continue

        # 2. （N）编号条目
        m = _ITEM_NUMBER_RE.match(stripped)
        if m:
            entry["type"] = "item_number"
            entry["number"] = int(m.group(1))
            entry["title"] = m.group(2).strip()
            catalog.append(entry)
            continue

        # 3. 知识点固定段头
        if any(stripped.startswith(s) for s in _KNOWLEDGE_SIGNALS):
            entry["type"] = "knowledge_signal"
            catalog.append(entry)
            continue

        # 4. 嵌入题目标记
        if _EXAM_MARKER_RE.match(stripped):
            entry["type"] = "exam_marker"
            catalog.append(entry)
            continue

        # 5. 题目信号
        if any(s in stripped for s in _EXAM_SIGNALS):
            entry["type"] = "exam_signal"
            catalog.append(entry)
            continue

        # 6. 方法/步骤标记
        if _METHOD_SIGNAL_RE.match(stripped):
            entry["type"] = "method_step"
            catalog.append(entry)
            continue

        # 7. 主题变体
        if _THEME_SIGNAL_RE.match(stripped):
            entry["type"] = "theme_variant"
            catalog.append(entry)
            continue

        # 8. 管理/跳过类信号
        if any(stripped.startswith(s) for s in _SKIP_SIGNALS):
            entry["type"] = "skip_signal"
            catalog.append(entry)
            continue

        # 9. 未分类（普通正文）
        entry["type"] = "content"
        catalog.append(entry)

    return {
        "catalog": catalog,
        "total_lines": len(lines),
        "total_chars": len(content),
    }


# ============================================================================
# 步骤 2 原稿保留（暂不改，后续调整 LLM prompt 使用新 catalog 格式）
# ============================================================================

_LLM_SPLIT_PROMPT = """你是语文教辅结构分析专家。系统已为一份知识讲义做了全文结构编目。
你需要基于编目清单，决定这份讲义应该如何切分为独立的校对单元。

## 输入

系统会提供：
1. 结构编目清单（每行一条记录：行号、信号类型、文本）
2. 部分段落的头尾上下文（用于确认边界）

## 切分原则

一个「校对单元」应该是内容上自封闭、LLM 可以在一次校对中完整处理的块。

- 每个 **（N）素材条目**（item_number 行）及其全部附属内容（寓意、角度、例句、文段示例）组成一个独立的校对单元
- 嵌入在素材条目中的补充题/例题**保留在原单元内**，不走题目校对
- 独立的**纯例题模块**（exam_marker 行，前后无素材讲解上下文）单独切出，走题目校对
- 文档开头的引导语/方法讲解（无 item_number 父级的内容）作为独立单元
- **skip_signal** 标记的内容可以不校对（分班标签、复习提示等管理信息）

## 输出格式

严格 JSON。只输出 unit 数组，每个 unit 只有 id 和 type：
{"units": [{"id":"L0016","type":"knowledge"}, ...]}

## 不该切的嵌入题（保留在素材单元内）

以下补充题嵌入在素材条目中，**不要**作为独立 unit：
- L0058 补充题一 → 嵌入在 L0042 汉阴丈人素材内
- L0094 补充题二 → 嵌入在 L0080 樗树无用之用素材内
- L0623 补充题四 → 嵌入在 L0587 萨特存在主义素材内

## 该切的独立练习题

以下标记是独立练习题块，应切为 exam：
- ### 练1 / ### 练2 / ### 练3 / ### 练4
- 补充题五（L0715，后无素材直接跟练习题）
- 补充题七（文档末尾独立作文题）

## 通用规则

- ### / #### 是容器层，不作为独立 unit，只切其下的 （N）素材条目
- 文档开头引导内容合并到 L0016 之前的同个知识单元
- 不确定类型选 knowledge
"""


def _build_llm_input(catalog: list[dict], content: str) -> str:
    """基于结构编目清单 + 原文段头尾，构建 LLM 输入。"""
    lines = content.split("\n")
    parts = []

    # 编目清单摘要
    parts.append("## 结构编目清单\n")
    type_counts = {}
    for entry in catalog:
        t = entry["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    parts.append(f"信号统计: {json.dumps(type_counts, ensure_ascii=False)}\n")
    parts.append("---\n")
    for entry in catalog:
        level_str = str(entry.get('level', '')) if entry.get('level') else ''
        eid = entry.get('id', f'L{entry["line"]:04d}')
        # 只发送关键边界类型的条目（非 content），大幅缩减输入
        if entry['type'] in ('heading', 'item_number', 'exam_marker'):
            parts.append(
                f"{eid}  [{entry['type']:18s}]  "
                f"{level_str:1s}  {entry['text'][:100]}"
            )

    # 段落上下文：给 LLM 确认边界用的原文内容
    parts.append("\n\n## 段落上下文（关键边界行的原文内容，用于确认切分）\n")
    boundary_indices = sorted(set(
        e["line"] for e in catalog
        if e["type"] in ("heading", "item_number", "exam_marker")
    ))
    boundary_indices_set = set(boundary_indices)
    for idx in boundary_indices:
        eid = f'L{idx:04d}'
        start = max(0, idx - 1)
        end = min(len(lines), idx + 5)
        snippet = "\n".join(f"L{i}: {lines[i]}" for i in range(start, end))
        parts.append(f"--- boundary {eid} ---\n{snippet}\n")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 步骤 2：LLM 块分类（仅处理 LOW + NONE 块）
# ---------------------------------------------------------------------------

ANCHOR_CLASSIFY_PROMPT = """你是语文教辅结构分析专家。系统已将文档分为若干区块，部分区块置信度较低，需要你帮忙识别其内容类型和边界。

## 输入格式

每个待分析区块格式为：
```
[BLOCK id=N from=L起始行]
{区块内容的前 500 字符 + 后 500 字符}
```

## 输出格式

严格输出 JSON，不要加任何解释：

```json
{
  "blocks": [
    {
      "id": "区块编号（整数）",
      "type": "knowledge | problem_strip | skip",
      "sub_blocks": [
        {"anchor": "子块锚点文本（原文中出现的唯一标题行或开头句，15-40字）",
         "type": "knowledge | problem_strip"}
      ]
    }
  ]
}
```

## 分类规则

- **knowledge**：素材条目（含典故/寓意/例句）、方法讲解、概念定义——这些需要知识类校对
- **problem_strip**：纯例题模块（含完整题目+解析+答案），无素材讲解——应拆出走题目校对
- **skip**：页眉页脚、版权信息、纯管理信息（如"分班型：目标清北班"）——不需要校对

## 子边界规则

- 如果区块内包含多个独立的知识单元（如多个素材条目），请用 sub_blocks 标注每个子块的锚点和类型
- 锚点必须是**原文中出现的原文行**，15-40 字，在该块内唯一。用锚点在原文中 grep 必须精确匹配一次
- 如果整个区块是单一类型、不需要细分，sub_blocks 为空数组
- 相邻子块的边界在下一个子块锚点的前一行

## 重要

- 锚点必须一字不差来自原文，确保可以在原文中 grep 精确定位
- 不确定类型时选 knowledge（宁可多校对，不可漏校对）
- 不要输出不全——如果区块包含 N 个字块，sub_blocks 必须有 N 个条目
"""


def _dump_intermediate(filename: str, content: str, doc_name: str = "") -> None:
    """保存中间产物到 output/中间产物/{doc_name}/ 目录。"""
    try:
        if doc_name:
            base = Path("output") / "中间产物" / doc_name
        else:
            base = Path("output") / "中间产物" / "knowledge_split"
        base.mkdir(parents=True, exist_ok=True)
        (base / filename).write_text(content, encoding="utf-8")
        log(f"   📄 中间产物已保存: {base / filename}")
    except Exception as e:
        log(f"   ⚠️ 保存中间产物失败: {e}")


def _extract_block_snippet(content: str, blk: dict, context_lines: int = 2) -> str:
    """提取块的头尾各 context_lines 行作为上下文。"""
    lines = content.split("\n")
    start, end = max(0, blk["from"] - context_lines), min(len(lines), blk["to"] + context_lines)
    snippet_lines = lines[start:end]
    # 截取前 500 和后 500 字符
    snippet = "\n".join(snippet_lines)
    if len(snippet) <= 1000:
        return snippet
    return snippet[:500] + "\n\n...（中间省略）...\n\n" + snippet[-500:]


def _classify_low_blocks(content: str, low_blocks: list[dict],
                         llm_callable, doc_name: str = "") -> list[dict]:
    """调用 LLM 对 LOW + NONE 置信度块进行分类。

    Args:
        content: 原始全文
        low_blocks: 步骤 1 输出的 LOW/NONE 置信度块列表
        llm_callable: LLM 调用函数，签名为 (user_text, system_prompt) -> str
        doc_name: 文档名（用于中间产物路径）

    Returns:
        与 low_blocks 一一对应的分类结果列表
    """
    if not low_blocks:
        return []

    # 构建 LLM 输入
    input_parts = []
    for blk in low_blocks:
        snippet = _extract_block_snippet(content, blk)
        input_parts.append(
            f"[BLOCK id={blk.get('id', '?')} from=L{blk['from']}]\n{snippet}\n"
        )
    user_text = "\n---\n".join(input_parts)

    # 保存 LLM 输入
    _dump_intermediate("_knowledge_scan_tree.json",
                       json.dumps({"low_blocks": low_blocks}, ensure_ascii=False, indent=2),
                       doc_name)
    _dump_intermediate("_knowledge_llm_input.txt", user_text, doc_name)

    log(f"   🤖 步骤 2：调用 LLM 分类 {len(low_blocks)} 个低置信度块...")

    try:
        raw = llm_callable(user_text, ANCHOR_CLASSIFY_PROMPT)
    except Exception as e:
        log(f"   ❌ 步骤 2 LLM 调用失败: {e}")
        _dump_intermediate("_knowledge_llm_error.txt",
                           f"调用异常: {e}\n\n{traceback.format_exc() if 'traceback' in dir() else str(e)}",
                           doc_name)
        raise

    _dump_intermediate("_knowledge_llm_raw.txt", raw, doc_name)

    # 解析 JSON
    try:
        # 提取 JSON 块（容错 LLM 可能在前后加了说明文字）
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            parsed = json.loads(json_match.group(0))
        else:
            raise ValueError("未找到 JSON 块")
        _dump_intermediate("_knowledge_llm_parsed.json",
                           json.dumps(parsed, ensure_ascii=False, indent=2),
                           doc_name)
        return parsed.get("blocks", [])
    except (json.JSONDecodeError, ValueError) as e:
        log(f"   ⚠️ LLM 返回 JSON 解析失败: {e}")
        _dump_intermediate("_knowledge_llm_parse_error.txt",
                           f"解析错误: {e}\n\n原始返回:\n{raw}", doc_name)
        # 降级：所有 LOW 块标记为 knowledge，不做细分
        fallback = []
        for blk in low_blocks:
            fallback.append({
                "id": blk.get("id", 0),
                "type": "knowledge",
                "sub_blocks": [],
            })
        return fallback


# ---------------------------------------------------------------------------
# 步骤 3：锚点合并 + 校验
# ---------------------------------------------------------------------------

def _merge_and_validate(content: str, high_blocks: list[dict],
                        classified_low_blocks: list[dict],
                        doc_name: str = "") -> list[dict]:
    """合并 HIGH + LOW/NONE 块的分类结果，生成最终锚点列表并校验。

    Returns:
        [{ "anchor": "...", "action": "start", "type": "knowledge" }, ...]
    """
    all_anchors = []

    # 处理 HIGH 块：类型按结构信号推断
    for blk in high_blocks:
        snippet = "\n".join(content.split("\n")[blk["from"]:blk["to"]])
        blk_type = _infer_block_type(snippet)
        all_anchors.append({
            "anchor": blk["anchor"],
            "action": "start",
            "type": blk_type,
            "from": blk["from"],
            "to": blk["to"],
            "source": "HIGH",
        })

    # 处理 LOW/NONE 分类结果
    for cls_blk in classified_low_blocks:
        if cls_blk.get("sub_blocks"):
            for sub in cls_blk["sub_blocks"]:
                all_anchors.append({
                    "anchor": sub["anchor"],
                    "action": "start",
                    "type": sub.get("type", "knowledge"),
                    "source": "LLM_sub",
                })
        elif cls_blk.get("type") != "skip":
            all_anchors.append({
                "anchor": cls_blk.get("anchor", ""),
                "action": "start",
                "type": cls_blk.get("type", "knowledge"),
                "source": "LLM_block",
            })

    # 按锚点在原文中最早出现的行号排序
    lines_list = content.split("\n")

    def _anchor_line(anchor_info):
        anchor = anchor_info["anchor"]
        # 优先精确匹配
        for i, line in enumerate(lines_list):
            if line.strip() == anchor.strip():
                return i
        # 回退：包含匹配
        for i, line in enumerate(lines_list):
            if anchor in line:
                return i
        return 999999

    all_anchors.sort(key=_anchor_line)

    # 校验：每个 anchor 在原文中唯一
    deduped = all_anchors

    # 校验：每个 anchor 在原文中唯一
    errors = []
    for a in deduped:
        count = content.count(a["anchor"])
        if count == 0:
            errors.append(f"锚点不存在: {a['anchor'][:60]}")
        elif count > 1 and a["source"] != "HIGH":
            errors.append(f"锚点出现 {count} 次（不唯一）: {a['anchor'][:60]}")

    _dump_intermediate("_knowledge_anchors.json",
                       json.dumps({"anchors": deduped, "errors": errors},
                                  ensure_ascii=False, indent=2),
                       doc_name)

    if errors:
        log(f"   ⚠️ 锚点校验发现 {len(errors)} 个问题，使用降级策略")
        # 降级：返回单单元
        return [{"anchor": content.split("\n")[0].strip() if content else "全文",
                 "action": "start", "type": "knowledge", "source": "fallback"}]

    return deduped


def _infer_block_type(snippet: str) -> str:
    """从块内容的结构信号推断类型。"""
    # 纯例题信号
    problem_signals = ["【详解】", "**审题：**", "**立意：**", "【参考例文】"]
    # 知识信号
    knowledge_signals = ["【寓意】", "【适用角度】", "【事例句运用】", "【标签化引用】"]

    p_score = sum(1 for s in problem_signals if s in snippet)
    k_score = sum(1 for s in knowledge_signals if s in snippet)

    if p_score > k_score and p_score >= 2:
        return "problem_strip"
    return "knowledge"


# ---------------------------------------------------------------------------
# 步骤 4：bash 逆序插入 + Python 复核
# ---------------------------------------------------------------------------

def _bash_insert_tags(content: str, anchors: list[dict],
                      doc_name: str = "") -> str:
    """用 bash (sed) 逆序在锚点位置插入知识标签。

    逆序处理保证前面的插入不影响后面锚点的行号。

    返回插入标签后的全文。
    """
    lines = content.split("\n")

    # 按锚点在原文中出现的行号逆序排列
    anchor_positions = []
    for i, line in enumerate(lines):
        for a in anchors:
            if a["anchor"] in line and a["anchor"] == line.strip():
                anchor_positions.append((i, a))
                break

    # 去重 + 逆序
    seen_lines = set()
    unique_positions = []
    for lno, a in reversed(anchor_positions):
        if lno not in seen_lines:
            unique_positions.append((lno, a))
            seen_lines.add(lno)
    unique_positions.sort(key=lambda x: x[0], reverse=True)

    # 逆序插入标签：在每个锚点切换位置插入 </knowledge><knowledge>
    # 按行号从高到低逆序处理，保证插入不影响前面锚点的行号
    result_lines = list(lines)

    # 逆序：从最远的锚点开始处理
    unique_positions.sort(key=lambda x: x[0], reverse=True)

    for lno, a in unique_positions:
        tag_type = a.get("type", "knowledge")
        # 在锚点行之前插入开始标签
        if tag_type == "problem_strip":
            result_lines.insert(lno, "<problem-strip>")
        else:
            result_lines.insert(lno, "<knowledge>")
        # 在锚点行之后插入上一个块的结束标签
        if tag_type == "problem_strip":
            result_lines.insert(lno + 2, "</problem-strip>")
        else:
            result_lines.insert(lno + 2, "</knowledge>")

    # 在最开头插入第一个开始标签（如果第一个锚点不在第 0 行）
    first_lno = unique_positions[-1][0] if unique_positions else 0  # 最小行号
    first_type = unique_positions[-1][1].get("type", "knowledge") if unique_positions else "knowledge"
    if first_lno > 0:
        if first_type == "problem_strip":
            result_lines.insert(0, "<problem-strip>")
        else:
            result_lines.insert(0, "<knowledge>")

    tagged = "\n".join(result_lines)
    _dump_intermediate("_knowledge_tagged.md", tagged, doc_name)

    return tagged


def _verify_tags(tagged: str, doc_name: str = "") -> dict:
    """复核标签配对 + 空单元检查。"""
    opens = tagged.count("<knowledge>")
    closes = tagged.count("</knowledge>")
    problems = tagged.count("<problem>")
    problem_closes = tagged.count("</problem>")

    result = {
        "knowledge_open": opens,
        "knowledge_close": closes,
        "paired": opens == closes,
        "problem_open": problems,
        "problem_close": problem_closes,
        "problem_paired": problems == problem_closes,
        "has_empty_unit": False,
        "ok": True,
    }

    # 检查空单元
    for start_tag in ["<knowledge>", "<problem>"]:
        end_tag = start_tag.replace("<", "</")
        pattern = re.escape(start_tag) + r"\s*" + re.escape(end_tag)
        if re.search(pattern, tagged):
            result["has_empty_unit"] = True
            break

    result["ok"] = result["paired"] and result["problem_paired"] and not result["has_empty_unit"]

    _dump_intermediate("_knowledge_verify.json",
                       json.dumps(result, ensure_ascii=False, indent=2),
                       doc_name)

    if not result["paired"]:
        log(f"   ⚠️ 标签不配对: {opens} 开 {closes} 闭")
    if result["has_empty_unit"]:
        log(f"   ⚠️ 存在空单元")

    return result


# ---------------------------------------------------------------------------
# 完整管线
# ---------------------------------------------------------------------------

def knowledge_split(content: str, llm_callable=None,
                    doc_name: str = "") -> list[dict]:
    """知识讲义智能切割完整管线。

    Args:
        content: 原始 Markdown 文本
        llm_callable: LLM 调用函数，签名为 (user_text, system_prompt) -> str
                      为 None 时跳过低置信度分类（纯 Python 切割）
        doc_name: 文档名（用于中间产物路径）

    Returns:
        [{ "content": "...", "type": "knowledge" | "problem_strip" }, ...]
    """
    log("📐 知识切割管线启动...")

    # 步骤 1
    log("   📊 步骤 1：结构扫描 + 置信度分层...")
    scan = _scan_structure(content)
    high_blocks = [b for b in scan["blocks"] if b["confidence"] == "HIGH"]
    low_blocks = [b for b in scan["blocks"] if b["confidence"] != "HIGH"]

    # 为 low_blocks 添加 id
    for idx, blk in enumerate(low_blocks):
        blk["id"] = idx

    log(f"   📊 HIGH: {len(high_blocks)} 块, LOW/NONE: {len(low_blocks)} 块")
    _dump_intermediate("_knowledge_scan_tree.json",
                       json.dumps(scan, ensure_ascii=False, indent=2),
                       doc_name)

    # 步骤 2（仅当有 LOW/NONE 块且有 LLM 调用函数时）
    classified = []
    if low_blocks and llm_callable:
        log(f"   🤖 步骤 2：LLM 处理 {len(low_blocks)} 个低置信度块...")
        try:
            classified = _classify_low_blocks(content, low_blocks, llm_callable, doc_name)
        except Exception as e:
            log(f"   ⚠️ LLM 分类失败: {e}，降级为单单元")
            return [{"content": content, "type": "knowledge"}]
    elif low_blocks:
        log(f"   ⚠️ {len(low_blocks)} 个低置信度块但无 LLM 调用函数，全部按 knowledge 处理")

    # 步骤 3
    log("   🔗 步骤 3：锚点合并 + 校验...")
    anchors = _merge_and_validate(content, high_blocks, classified, doc_name)

    # 单单元情况（锚点 ≤ 1）
    if len(anchors) <= 1:
        log("   📄 单单元模式：全文作为一个校对单元")
        # 推断整体类型
        blk_type = _infer_block_type(content)
        return [{"content": content, "type": blk_type}]

    # 步骤 4
    log("   🔧 步骤 4：bash 逆序插入 + 复核...")
    try:
        tagged = _bash_insert_tags(content, anchors, doc_name)
    except Exception as e:
        log(f"   ⚠️ bash 插入失败: {e}，降级为单单元")
        return [{"content": content, "type": "knowledge"}]

    _ = _verify_tags(tagged, doc_name)

    # 解析切割结果
    problems = _parse_knowledge_tags(tagged)

    if not problems:
        log("   ⚠️ 切割未产生有效单元，降级为单单元")
        return [{"content": content, "type": "knowledge"}]

    # 类型统计
    type_counts = {}
    for p in problems:
        t = p.get("type", "knowledge")
        type_counts[t] = type_counts.get(t, 0) + 1
    log(f"   ✅ 切割完成: {len(problems)} 个单元 ({type_counts})")

    return problems


def _parse_knowledge_tags(tagged: str) -> list[dict]:
    """从带标签的文本中解析知识单元。

    支持 <knowledge>...</knowledge> 和 <problem-strip>...</problem-strip> 两种标签。
    """
    results = []

    # 解析 <knowledge> 标签
    knowledge_pattern = re.compile(r'<knowledge>(.*?)</knowledge>', re.DOTALL)
    for m in knowledge_pattern.finditer(tagged):
        content = m.group(1).strip()
        if content:
            # 检查内部是否有 <problem> 嵌套（无需单独拆，保留在原块中）
            results.append({"content": content, "type": "knowledge"})

    # 解析 <problem-strip> 标签（单独的题目块）
    ps_pattern = re.compile(r'<problem-strip>(.*?)</problem-strip>', re.DOTALL)
    for m in ps_pattern.finditer(tagged):
        content = m.group(1).strip()
        if content:
            results.append({"content": content, "type": "problem_strip"})

    # 如果以上都未匹配，回退：整篇作为一个 knowledge 块
    if not results and tagged.strip():
        # 移除可能残留的标签
        clean = re.sub(r'</?knowledge>', '', tagged)
        clean = re.sub(r'</?problem-strip>', '', clean)
        if clean.strip():
            results.append({"content": clean.strip(), "type": "knowledge"})

    return results


def knowledge_split_smart(md_content: str, api_url: str, api_key: str,
                          model: str, md_file: str = None) -> list[dict]:
    """智能切割的对外接口：含 LLM 调用。

    与 smart_split.py 的 smart_split() 接口一致，方便 subject.py 中替换调用。
    """
    from core.api_client import call_api

    doc_name = ""
    if md_file:
        doc_name = Path(md_file).stem
        if doc_name.endswith("_raw"):
            doc_name = doc_name[:-4]

    def _llm_call(user_text: str, system_prompt: str) -> str:
        try:
            result = call_api(
                api_url=api_url,
                api_key=api_key,
                model=model,
                md_text=user_text,
                images=[],
                q_title="知识切割",
                system_prompt=system_prompt,
                tools=[],
                max_loops=1,
                max_tokens=4096,
                output_dir=str(Path("output") / "中间产物" / doc_name) if doc_name else None,
            )
            content = result.get("content", "")
            # 保存 LLM 工具调用记录
            if result.get("tool_calls_log"):
                _dump_intermediate("_knowledge_llm_tool_calls.json",
                                   json.dumps(result["tool_calls_log"],
                                              ensure_ascii=False, indent=2),
                                   doc_name)
            return content
        except Exception as e:
            log(f"   ❌ LLM 调用异常: {e}")
            raise

    return knowledge_split(md_content, llm_callable=_llm_call, doc_name=doc_name)
