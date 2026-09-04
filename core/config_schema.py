"""配置 Schema 验证 —— Pydantic 模型 + 启动时校验。

在 config_loader.load_config() 中调用 validate_config()，
拼写错误和字段缺失不再静默失效。
"""
import json
import os


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

    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    errors = []

    # ---- 类型检查 ----
    if "knowledge_agent_prompt_lines" in raw:
        value = raw["knowledge_agent_prompt_lines"]
        if not isinstance(value, list):
            errors.append("'knowledge_agent_prompt_lines' 必须是字符串数组")
        elif not all(isinstance(x, str) for x in value):
            errors.append("'knowledge_agent_prompt_lines' 的元素必须是字符串")

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

    # agent_prompt.json —— 校对提示词唯一来源（ADR-00XX 移除 question_prompt_lines 回退后必填）。
    # 缺失/非法即中断加载（fail-fast），避免静默回退到旧提示词造成双源不同步。
    agent_file = os.path.join(subject_dir, "agent_prompt.json")
    if not os.path.exists(agent_file):
        errors.append(f"缺少 提示词文件 '{os.path.basename(agent_file)}'（校对提示词唯一来源，缺失时无法校对，请重新发起校对）")
    else:
        try:
            with open(agent_file, encoding="utf-8") as f:
                agent_data = json.load(f)
            agent_lines = agent_data.get("agent_prompt_lines", [])
            if not isinstance(agent_lines, list):
                errors.append("'agent_prompt_lines' 必须是字符串数组")
            elif len(agent_lines) == 0:
                errors.append("'agent_prompt_lines' 不能为空")
            elif not all(isinstance(x, str) for x in agent_lines):
                errors.append("'agent_prompt_lines' 的元素必须是字符串")
            config["agent_prompt_lines"] = agent_lines
        except Exception as e:
            errors.append(f"加载 {os.path.basename(agent_file)} 失败: {e}")

    # agent_prompt 校验错误与 config.json 错误同样需要中断加载
    if errors:
        raise ValueError(
            f"配置文件校验失败: {config_path}\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    return config
