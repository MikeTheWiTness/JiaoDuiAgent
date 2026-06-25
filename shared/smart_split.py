import re
from core.logging_utils import log
from core.api_client import call_api


SMART_SPLIT_PROMPT = """你是专业的语文试卷结构分析专家。请在给定的文档原文中，用 <problem></problem> 标签标记每个完整的题目单元。

规则：
1. **绝对不修改原文任何一个字**，只在题目边界插入标签
2. 每个完整题目单元（一篇文言文+几道小题、一首诗+鉴赏题等）用一对 <problem> 标签包裹
3. 引言、说明、过渡文字、参考答案等非题目内容不标记
4. 标签必须单独占一行，不要和正文混在一起
5. 输出完整的带标签文本，不要加其他解释

示例：
```
这是引言，不标记
<problem>
例1 题目内容...
</problem>
中间过渡文字，不标记
<problem>
例2 题目内容...
</problem>
结尾总结，不标记
```"""


def parse_problem_tags(text):
    pattern = r"<problem>(.*?)</problem>"
    matches = re.findall(pattern, text, re.DOTALL)
    return [{"content": m.strip()} for m in matches]


def smart_split_with_callable(md_content, llm_callable):
    for attempt in range(2):
        try:
            result_text = llm_callable(md_content, SMART_SPLIT_PROMPT)
        except Exception as e:
            log(f"   ⚠️ 智能分割第 {attempt+1} 次调用失败: {e}")
            continue

        problems = parse_problem_tags(result_text)
        problems = [p for p in problems if p["content"].strip()]
        if problems:
            log(f"   ✅ 智能分割成功，识别到 {len(problems)} 个题目单元")
            return problems

        log(f"   ⚠️ 第 {attempt+1} 次未识别到有效题目标记")

    log(f"   ⚠️ 智能分割失败，降级为单单元")
    return [{"content": md_content}]


def smart_split(md_content, api_url, api_key, model):
    def _llm_call(text, prompt):
        result, _ = call_api(
            api_url, api_key, model,
            text, [], "智能分割",
            prompt, tools=[], max_loops=1
        )
        return result

    return smart_split_with_callable(md_content, _llm_call)
