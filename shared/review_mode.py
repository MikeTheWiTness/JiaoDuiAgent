"""批注评审模式工具 —— 批注提取、评审提示词、结果解析。"""
import re


def is_review_mode(source_mode):
    return source_mode == "批注评审"


def extract_comments_from_md(md_text):
    if not md_text:
        return []

    pattern = r'\[📝批注(\d+)：([^\]]+)\]'
    comments = []
    for match in re.finditer(pattern, md_text):
        cid = int(match.group(1))
        text = match.group(2).strip()
        start = match.start()
        end = match.end()

        context_before = md_text[max(0, start - 50):start]
        context_after = md_text[end:min(len(md_text), end + 50)]

        comments.append({
            "id": cid,
            "text": text,
            "position": start,
            "context_before": context_before,
            "context_after": context_after,
        })

    comments.sort(key=lambda c: c["id"])
    return comments


def build_review_prompt(question_md):
    comments = extract_comments_from_md(question_md)

    prompt = """## 任务：批注评审

你是一位资深语文教研员，需要对已有人工批注的试卷/文档进行评审。

### 你的职责
1. **逐条评审已有批注**：判断每条批注的正确性
   - ✅ 正确：批注完全准确
   - ⚠️ 部分正确：批注有一定道理但不完全准确
   - ❌ 有误：批注错误或不成立

2. **补充发现遗漏错误**：除了已有批注外，你自己再通读全文，找出被遗漏的错误

### 批注列表
"""

    if comments:
        for c in comments:
            prompt += f"\n- **批注{c['id']}**：{c['text']}"
    else:
        prompt += "\n（本文档中未识别到批注，请直接进行校对，找出所有错误）"

    prompt += """

### 输出格式要求

请严格按照以下格式输出：

---

## 批注评审结果

### 批注1
- 评判：正确 / 部分正确 / 有误
- 说明：（简要说明理由）

### 批注2
- 评判：正确 / 部分正确 / 有误
- 说明：（简要说明理由）

...（逐条列出所有批注）

### 补充发现
- （第一处遗漏的错误及其说明）
- （第二处遗漏的错误及其说明）
- ...

---

### 注意事项
- 有答案时先校答案，无答案时校题干
- 文言文/诗歌优先查阅权威原文
- 每条批注都必须给出评判，不得遗漏
- 补充发现要具体说明位置和错误类型
- 如果没有补充发现，写"暂无补充发现"
"""

    return prompt


def parse_review_result(result_text):
    if not result_text:
        return {"judgments": [], "supplements": []}

    judgments = []
    supplements = []

    comment_pattern = r'###\s*批注(\d+)\s*\n(.*?)(?=\n###|\n##|$)'
    for match in re.finditer(comment_pattern, result_text, re.DOTALL):
        cid = int(match.group(1))
        body = match.group(2)

        verdict_match = re.search(r'评判[：:]\s*(\S+)', body)
        verdict = verdict_match.group(1).strip() if verdict_match else "未评判"

        reason_match = re.search(r'说明[：:]\s*(.+)', body)
        reason = reason_match.group(1).strip() if reason_match else ""

        judgments.append({
            "id": cid,
            "verdict": verdict,
            "reason": reason,
        })

    supp_pattern = r'###\s*补充发现\s*\n(.*?)(?=\n###|\n##|$)'
    supp_match = re.search(supp_pattern, result_text, re.DOTALL)
    if supp_match:
        supp_text = supp_match.group(1)
        for line in supp_text.splitlines():
            line = line.strip()
            if line.startswith("-") or line.startswith("•"):
                item = line[1:].strip()
                if item and "暂无" not in item:
                    supplements.append(item)

    judgments.sort(key=lambda j: j["id"])

    return {
        "judgments": judgments,
        "supplements": supplements,
    }
