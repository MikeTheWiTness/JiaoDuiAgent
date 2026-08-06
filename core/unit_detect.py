"""目录单元识别 —— 单一真源，供 UI 与 proofread 共用（ADR-0022 C2.3）。"""

import re
from pathlib import Path

# 前缀锚定（非 fullmatch）：保留「第1题_备份」「第1题(文言文)」等合法变体，
# 拒绝「试题」「错题本」等任意含「题」的误报
_UNIT_DIR_RE = re.compile(r'^(第\d+题|板块\d+|单元\d+)')


def is_unit_dir(name: str) -> bool:
    """判断目录名是否为校对单元目录。

    识别模式：
    - 第N题（如 第1题、第12题）
    - 板块N（如 板块1、板块2）
    - 单元N（如 单元1、单元12，ADR-0019 C3.14）

    注意：此函数接受纯目录名（不含路径），不判断是否为目录。
    """
    return bool(_UNIT_DIR_RE.match(name))


def scan_question_dirs(root: Path) -> list[Path]:
    """扫描根目录下的校对单元目录列表。

    遍历 root 的一级子目录，识别「题」「板块」「单元」关键字。
    若一级无匹配，检查二级子目录。

    Args:
        root: 根目录路径

    Returns:
        匹配的目录路径列表
    """
    result = []
    sub_items = [x for x in root.iterdir() if x.is_dir()]
    sub_names = [x.name for x in sub_items]
    has_question_dir = any(is_unit_dir(n) for n in sub_names)
    has_knowledge = any(n == '知识' for n in sub_names)
    if has_question_dir or has_knowledge:
        result.append(str(root))
    else:
        for d in sub_items:
            inner = [x.name for x in d.iterdir() if x.is_dir()]
            if any(is_unit_dir(n) for n in inner) or '知识' in inner:
                result.append(str(d))
    return [Path(p) for p in result]
