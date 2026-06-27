import os, re, json, logging
_log = logging.getLogger(__name__)
_config_cache = {}

def clear_config_cache():
    _config_cache.clear()

def load_config(subject_dir):
    cache_key = subject_dir
    cached = _config_cache.get(cache_key)
    if cached is not None:
        return cached
    config_file = os.path.join(subject_dir, "config.json")
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"config not found: {config_file}")
    with open(config_file, encoding="utf-8") as f:
        new_data = json.load(f)
    if "question_prompt_lines" not in new_data:
        raise ValueError(f"missing question_prompt_lines: {config_file}")
    if "knowledge_prompt_lines" not in new_data:
        raise ValueError(f"missing knowledge_prompt_lines: {config_file}")
    config = {}
    config["question_prompt_lines"] = new_data["question_prompt_lines"]
    config["knowledge_prompt_lines"] = new_data["knowledge_prompt_lines"]
    config["agent_prompt_lines"] = new_data.get("agent_prompt_lines", None)
    lecture = new_data.get("lecture_split", {})
    config["lecture_split_mode"] = lecture.get("split_mode", "title")
    config["lecture_section_pattern"] = lecture.get("section_pattern", r"^##\s")
    config["lecture_wrapped_patterns"] = lecture.get("wrapped_patterns", [])
    config["lecture_unwrapped_patterns"] = lecture.get("unwrapped_patterns", [])
    config["lecture_section_boundary"] = lecture.get("section_boundary", True)
    exam = new_data.get("exam_split", {})
    config["exam_question_pattern"] = exam.get("question_pattern", r"^(\\d+)\\uff0e")
    _config_cache[cache_key] = config
    return config

def get_agent_prompt(config):
    return config.get("agent_prompt_lines", None)
