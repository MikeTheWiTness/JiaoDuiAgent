"""配置 Schema 验证 —— Pydantic 模型 + 启动时校验。

在 config_loader.load_config() 中调用 validate_config()，
拼写错误和字段缺失不再静默失效。
"""
import json
import os
from pathlib import Path
from typing import Optional


def validate_config(subject_dir) -> dict:
    """读取并校验学科的 config.json。

    Returns:
        校验通过的配置 dict（含默认值填充）

    Raises:
        ValueError: 配置不合法，消息含文件名和具体字段
    """
    config_path = os.path.join(subject_dir, "config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    errors = []

    # ---- 必填字段 ----
    for field in ["question_prompt_lines"]:
        if field not in raw:
            errors.append(f"缺少必填字段 '{field}'")
        elif not isinstance(raw[field], list) or len(raw[field]) == 0:
            errors.append(f"'{field}' 必须是非空字符串数组")

    # ---- 类型检查 ----
    if "knowledge_agent_prompt_lines" in raw:
        if not isinstance(raw["knowledge_agent_prompt_lines"], list):
            errors.append("'knowledge_agent_prompt_lines' 必须是字符串数组")

    if "lecture_split" in raw:
        ls = raw["lecture_split"]
        if not isinstance(ls, dict):
            errors.append("'lecture_split' 必须是对象")
        else:
            for key in ["wrapped_patterns", "unwrapped_patterns", "section_pattern_extensions"]:
                if key in ls and not isinstance(ls[key], list):
                    errors.append(f"'lecture_split.{key}' 必须是数组")

    if "exam_split" in raw:
        es = raw["exam_split"]
        if not isinstance(es, dict):
            errors.append("'exam_split' 必须是对象")
        elif "question_pattern" in es and not isinstance(es["question_pattern"], str):
            errors.append("'exam_split.question_pattern' 必须是字符串")

    if errors:
        raise ValueError(
            f"配置文件校验失败: {config_path}\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    # ---- 构建标准化配置（含默认值） ----
    lecture = raw.get("lecture_split", {})
    exam = raw.get("exam_split", {})

    config = {
        "question_prompt_lines": raw["question_prompt_lines"],
        "lecture_split_mode": lecture.get("split_mode", "section"),
        "lecture_section_pattern": lecture.get("section_pattern", r"^##\s"),
        "lecture_section_extensions": lecture.get("section_pattern_extensions", []),
        "lecture_wrapped_patterns": lecture.get("wrapped_patterns", []),
        "lecture_unwrapped_patterns": lecture.get("unwrapped_patterns", []),
        "lecture_section_boundary": lecture.get("section_boundary", True),
        "exam_question_pattern": exam.get("question_pattern", r"^(\d+)．"),
    }

    # 可选字段
    if "knowledge_agent_prompt_lines" in raw:
        config["knowledge_agent_prompt_lines"] = raw["knowledge_agent_prompt_lines"]

    # agent_prompt.json（独立文件，不存在不报错）
    agent_file = os.path.join(subject_dir, "agent_prompt.json")
    if os.path.exists(agent_file):
        try:
            with open(agent_file, "r", encoding="utf-8") as f:
                agent_data = json.load(f)
            config["agent_prompt_lines"] = agent_data.get("agent_prompt_lines", [])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"加载 agent_prompt.json 失败: {e}")

    return config
