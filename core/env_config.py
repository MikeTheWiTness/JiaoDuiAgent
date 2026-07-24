import os
import traceback

from core.logging_utils import log


def load_env_config(subject_dir):
    cfg = {"api_url": "", "api_key": "", "model_name": ""}
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
    except Exception:
        log(f"   ⚠️ 读取 .env 文件失败 ({env_file}):\n{traceback.format_exc()}")
    return cfg


def save_env_config(subject_dir, api_url, api_key, model_name):
    env_file = os.path.join(subject_dir, ".env")
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(f"API_URL={api_url}\n")
        f.write(f"API_KEY={api_key}\n")
        f.write(f"MODEL_NAME={model_name}\n")
