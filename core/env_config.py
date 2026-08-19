import os
import traceback

from core.logging_utils import log


def load_env_config(subject_dir):
    cfg = {"api_url": "", "api_key": "", "model_name": "", "api_format": "chat/completions"}
    env_file = os.path.join(subject_dir, ".env")
    if not os.path.exists(env_file):
        return cfg
    try:
        with open(env_file, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key == 'api_url':
                        cfg['api_url'] = val
                    elif key == 'api_key':
                        cfg['api_key'] = val
                    elif key == 'model_name':
                        cfg['model_name'] = val
                    elif key == 'api_format':
                        cfg['api_format'] = val or "chat/completions"
    except Exception:
        log(f"   ⚠️ 读取 .env 文件失败 ({env_file}):\n{traceback.format_exc()}")
    return cfg


def save_env_config(subject_dir, api_url, api_key, model_name, api_format="chat/completions"):
    """保存 API 凭证到 .env 文件，保留现有额外键与注释。

    改为读改写策略：先读取现有 .env 的全部行，仅修改匹配的四键行；
    不存在的键在原注释段后追加。不再覆写整个文件。
    """
    env_file = os.path.join(subject_dir, ".env")
    key_map = {
        "api_url": api_url,
        "api_key": api_key,
        "model_name": model_name,
        "api_format": api_format,
    }

    if os.path.exists(env_file):
        lines = []
        updated_keys = set()
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _ = stripped.split("=", 1)
                    key_lower = key.strip().lower()
                    if key_lower in key_map:
                        lines.append(f"{key.strip()}={key_map[key_lower]}\n")
                        updated_keys.add(key_lower)
                        continue
                lines.append(line)

        # 补写未在原文件中出现的键
        for k, v in key_map.items():
            if k not in updated_keys:
                lines.append(f"{k.upper()}={v}\n")

        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(lines)
    else:
        # 文件不存在时新建（行为与原实现一致）
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"API_URL={api_url}\n")
            f.write(f"API_KEY={api_key}\n")
            f.write(f"MODEL_NAME={model_name}\n")
            f.write(f"API_FORMAT={api_format}\n")
