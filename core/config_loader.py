import os, re, json, logging
from core.config_schema import validate_config

_log = logging.getLogger(__name__)

_config_cache = {}


def clear_config_cache():
    _config_cache.clear()


def load_config(subject_dir):
    cache_key = subject_dir
    cached = _config_cache.get(cache_key)
    if cached is not None:
        return cached

    # 校验 + 标准化（失败时抛出含文件名和字段的明确错误）
    config = validate_config(subject_dir)

    _config_cache[cache_key] = config
    return config


def get_question_prompt(config):
    prompt = config["question_prompt_lines"]
    if isinstance(prompt, list):
        prompt = "\n".join(prompt)
    return prompt


def get_knowledge_prompt(config):
    prompt = config["knowledge_prompt_lines"]
    if isinstance(prompt, list):
        prompt = "\n".join(prompt)
    return prompt


def get_lecture_patterns(config):
    wrapped = []
    for pat in config["lecture_wrapped_patterns"]:
        try:
            full_pat = r'^\*\*' + pat + r'\*\*.*$'
            wrapped.append(re.compile(full_pat))
        except re.error:
            _log.warning("无效正则 (wrapped): %r", pat)
    unwrapped = []
    for pat in config["lecture_unwrapped_patterns"]:
        try:
            unwrapped.append(re.compile(pat))
        except re.error:
            _log.warning("无效正则 (unwrapped): %r", pat)
    return wrapped, unwrapped


def get_compiled_title_patterns(config):
    wrapped, unwrapped = get_lecture_patterns(config)
    return wrapped + unwrapped


def get_section_boundary_enabled(config):
    return config.get("lecture_section_boundary", True)


def get_lecture_split_mode(config):
    return config.get("lecture_split_mode", "section")


# 默认 section_pattern（ADR-0017 决策1）：匹配 ##/### 标题 + 例题标记 + 通用知识标题
DEFAULT_SECTION_PATTERN = (
    r"^#{2,3}\s"                       # ## / ### 标题
    r"|^\*\*(例|练|变式|真题)\d+\*\*"    # **例1**、**练1**、**变式1**、**真题1**
    r"|^\*\*教师版\*\*"                 # **教师版**
    r"|必备知识"                         # 通用知识标题
    r"|模型大招"                         # 方法/模型总结标题
    r"|重难点突破"                        # 重难点专题标题
)


def get_section_pattern(config):
    """构建 section_pattern：基础 pattern + 学科扩展。

    如果 config 中显式设置了 section_pattern，直接使用；
    否则从 DEFAULT_SECTION_PATTERN + section_pattern_extensions 构建。
    """
    raw = config.get("lecture_section_pattern", "")
    if raw and raw != r"^##\s":
        # 显式设置了自定义 pattern，直接使用
        try:
            return re.compile(raw)
        except re.error:
            return re.compile(DEFAULT_SECTION_PATTERN)

    # 使用默认 pattern + 学科扩展
    extensions = config.get("lecture_section_extensions", [])
    pattern = DEFAULT_SECTION_PATTERN
    for ext in extensions:
        pattern += "|" + re.escape(ext)
    try:
        return re.compile(pattern)
    except re.error:
        return re.compile(DEFAULT_SECTION_PATTERN)


def get_exam_question_pattern(config):
    try:
        return re.compile(config["exam_question_pattern"])
    except re.error:
        return re.compile(r"^(\d+)．")



def get_agent_prompt(config):
    return config.get("agent_prompt_lines", None)
