"""格式审查二级制：程序初筛 + LLM 格式修正。"""
import re
from core.api_client import call_api_continue


def _is_no_issue(res: str) -> bool:
    if not res:
        return False
    stripped = res.strip()
    if stripped == "无问题":
        return True
    if stripped.startswith("无问题") and len(stripped) <= 10:
        return True
    return False


def _enforce_format(res: str):
    if _is_no_issue(res):
        return True, ""
    issues = []
    marker_match = re.search(r'###\s*标记原文\s*\n(.*?)(?=\n###\s|\Z)', res, re.DOTALL)
    reason_match = re.search(r'###\s*修改原因\s*\n(.*?)(?=\n###\s|\Z)', res, re.DOTALL)
    if not marker_match:
        issues.append("缺少 ### 标记原文 段落")
    if not reason_match:
        issues.append("缺少 ### 修改原因 段落")
    if marker_match and reason_match:
        markers = re.findall(r'【(\d+)\|', marker_match.group(1))
        marker_nums = set(int(m) for m in markers)
        reason_nums = set()
        for line in reason_match.group(1).split('\n'):
            m = re.match(r'^(\d+)\.\s', line.strip())
            if m:
                reason_nums.add(int(m.group(1)))
        missing = marker_nums - reason_nums
        extra = reason_nums - marker_nums
        if missing:
            issues.append(f"标记编号 {sorted(missing)} 在修改原因中缺少对应条目")
        if extra:
            issues.append(f"修改原因编号 {sorted(extra)} 没有对应的标记")
    if marker_match:
        malformed = re.findall(r'【(?!\d+\|)', marker_match.group(1))
        if malformed:
            issues.append(f"发现 {len(malformed)} 个格式异常的标记（编号后缺少 |）")
    if issues:
        return False, "; ".join(issues)
    return True, ""


def _llm_format_fix(res, issues_desc, api_url, api_key, model):
    follow_up = (
        f"校对结果格式问题：{issues_desc}\n\n"
        "请按规范格式重组：\n"
        "1. 包含 ### 标记原文 段落（完整题目原文+内联标记）\n"
        "2. 包含 ### 修改原因 段落（标记编号与原因一一对应）\n"
        "3. 不改变任何校对结论\n\n"
        f"原始输出：\n{res}"
    )
    try:
        result = call_api_continue(api_url, api_key, model, [], follow_up)
        content = result["content"]
        if content and "API调用失败" not in content:
            return content
    except Exception:
        pass
    return None


def enforce_and_fix(res, api_url, api_key, model):
    ok, issues = _enforce_format(res)
    if ok:
        return res, False, ""
    fixed = _llm_format_fix(res, issues, api_url, api_key, model)
    if fixed and _enforce_format(fixed)[0]:
        return fixed, True, issues
    return res, False, issues
