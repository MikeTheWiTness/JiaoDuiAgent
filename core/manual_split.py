import re


# ─── 统一的单元标记（ADR-0017 决策5） ──────────────────────────

UNIT_START_MARKER = r"(\\?#){6}\s*单元开始\s*(\\?#){6}"
UNIT_END_MARKER = r"(\\?#){6}\s*单元结束\s*(\\?#){6}"


class UnitMarkerError(ValueError):
    """统一的单元标记错误。"""
    pass


# ─── 旧的标记（向后兼容，后续移除） ────────────────────────────

START_MARKER = r"(\\?#){6}\s*题目开始\s*(\\?#){6}"
END_MARKER = r"(\\?#){6}\s*题目结束\s*(\\?#){6}"

class ManualMarkerError(ValueError):
    pass


# ─── 共用的单元解析器 ────────────────────────────────────────

def parse_unit_markers(text: str) -> list[dict]:
    """解析 ###### 单元开始/结束 ###### 标记，返回单元列表。

    供 manual_split 和 smart_split 共用。
    容忍 pandoc 转义的 \\# 前缀。

    Returns:
        [{"content": "单元正文"}, ...]

    Raises:
        UnitMarkerError: 标记缺失或不配对
    """
    lines = text.splitlines()
    units = []
    current_content = []
    in_unit = False
    start_count = 0
    end_count = 0

    start_pattern = f"^{UNIT_START_MARKER}$"
    end_pattern = f"^{UNIT_END_MARKER}$"

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_start = bool(re.match(start_pattern, stripped))
        is_end = bool(re.match(end_pattern, stripped))

        if is_start:
            start_count += 1
            if in_unit:
                raise UnitMarkerError(
                    f"第 {i} 行：发现未闭合的单元开始标记，标记不配对"
                )
            in_unit = True
            current_content = []
        elif is_end:
            end_count += 1
            if not in_unit:
                raise UnitMarkerError(
                    f"第 {i} 行：发现没有对应开始标记的单元结束标记，标记不配对"
                )
            units.append({"content": "\n".join(current_content)})
            in_unit = False
        else:
            if in_unit:
                current_content.append(line)

    if start_count == 0 and end_count == 0:
        raise UnitMarkerError(
            "未找到任何单元标记（###### 单元开始 ###### / ###### 单元结束 ######），"
            "请在文档中添加成对标记"
        )

    if in_unit:
        raise UnitMarkerError(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记，"
            f"最后一个单元缺少结束标记"
        )

    if start_count != end_count:
        raise UnitMarkerError(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记"
        )

    return units


# ─── 统一的单元拆分入口 ──────────────────────────────────────

def split_by_unit_markers(md_content: str) -> list[dict]:
    """按 ###### 单元开始/结束 ###### 标记拆分。

    替代原有的 split_by_manual_markers()。
    """
    return parse_unit_markers(md_content)


# ─── 旧的拆分函数（向后兼容，委托到新函数） ──────────────────

def _split_by_deprecated_markers(md_content, unit_label, start_pattern, end_pattern, error_cls):
    """旧的内部实现，保留以支持旧的题目/知识标记。"""
    lines = md_content.splitlines()
    problems = []
    current_content = []
    in_problem = False
    start_count = 0
    end_count = 0

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_start = bool(re.match(f"^{start_pattern}$", stripped))
        is_end = bool(re.match(f"^{end_pattern}$", stripped))

        if is_start:
            start_count += 1
            if in_problem:
                raise error_cls(
                    f"第 {i} 行：发现未闭合的{unit_label}开始标记，标记不配对"
                )
            in_problem = True
            current_content = []
        elif is_end:
            end_count += 1
            if not in_problem:
                raise error_cls(
                    f"第 {i} 行：发现没有对应开始标记的{unit_label}结束标记，标记不配对"
                )
            problems.append({"content": "\n".join(current_content)})
            in_problem = False
        else:
            if in_problem:
                current_content.append(line)

    if start_count == 0 and end_count == 0:
        raise error_cls(
            f"未找到任何{unit_label}标记（###### {unit_label}开始 ###### / ###### {unit_label}结束 ######），"
            "请在文档中添加成对标记"
        )

    if in_problem:
        raise error_cls(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记，"
            f"最后一个{unit_label}缺少结束标记"
        )

    if start_count != end_count:
        raise error_cls(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记"
        )

    return problems


def split_by_manual_markers(md_content):
    """旧的题目标记拆分（向后兼容）。"""
    return _split_by_deprecated_markers(md_content, "题目", START_MARKER, END_MARKER, ManualMarkerError)
