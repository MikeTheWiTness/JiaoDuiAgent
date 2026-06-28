import re


START_MARKER = r"(\\?#){6}\s*题目开始\s*(\\?#){6}"
END_MARKER = r"(\\?#){6}\s*题目结束\s*(\\?#){6}"


class ManualMarkerError(ValueError):
    pass


def split_by_manual_markers(md_content):
    lines = md_content.splitlines()
    problems = []
    current_content = []
    in_problem = False
    start_count = 0
    end_count = 0

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_start = bool(re.match(f"^{START_MARKER}$", stripped))
        is_end = bool(re.match(f"^{END_MARKER}$", stripped))

        if is_start:
            start_count += 1
            if in_problem:
                raise ManualMarkerError(
                    f"第 {i} 行：发现未闭合的题目开始标记，标记不配对"
                )
            in_problem = True
            current_content = []
        elif is_end:
            end_count += 1
            if not in_problem:
                raise ManualMarkerError(
                    f"第 {i} 行：发现没有对应开始标记的题目结束标记，标记不配对"
                )
            problems.append({"content": "\n".join(current_content)})
            in_problem = False
        else:
            if in_problem:
                current_content.append(line)

    if start_count == 0 and end_count == 0:
        raise ManualMarkerError(
            "未找到任何题目标记（###### 题目开始 ###### / ###### 题目结束 ######），"
            "请在文档中添加成对标记"
        )

    if in_problem:
        raise ManualMarkerError(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记，"
            "最后一个题目缺少结束标记"
        )

    if start_count != end_count:
        raise ManualMarkerError(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记"
        )

    return problems
