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
    return config.get("lecture_split_mode", "title")


def get_section_pattern(config):
    try:
        return re.compile(config.get("lecture_section_pattern", r"^##\s"))
    except re.error:
        return re.compile(r"^##\s")


def get_exam_question_pattern(config):
    try:
        return re.compile(config["exam_question_pattern"])
    except re.error:
        return re.compile(r"^(\d+)．")



def get_agent_prompt(config):
    return config.get("agent_prompt_lines", None)
