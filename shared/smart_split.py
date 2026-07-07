import re
import os
from pathlib import Path
from core.logging_utils import log
from core.api_client import call_api
from core.manual_split import parse_unit_markers


SMART_SPLIT_PROMPT = """你是专业的语文试卷结构分析专家。请在给定的文档原文中，用 ###### 单元开始 ###### 和 ###### 单元结束 ###### 标记每个完整的单元。

规则：
1. **绝对不修改原文任何一个字**，只在单元边界插入标记
2. 每个完整单元（一篇文言文+几道小题、知识讲解+配套练习、一首诗+鉴赏题等）用一对标记包裹
3. **答案解析是题目的一部分**：如果某道题后面紧跟着答案、解析、参考答案等内容，必须将它们也包含在同一个单元内
4. **仅跳过**：试卷级别的标题、总分说明、考试时间等全局信息。这些不属于任何一个单元
5. 标记必须**单独占一行**，不要和正文混在一起
6. 输出完整的带标记文本，不要加其他解释

示例：
```
这是引言，不标记
###### 单元开始 ######
例1 题目内容...
###### 单元结束 ######
中间过渡文字，不标记
###### 单元开始 ######
例2 题目内容...
###### 单元结束 ######
结尾总结，不标记
```"""


SMART_SPLIT_MAX_TOKENS = 16384


def parse_problem_tags(text):
    """旧的 <problem> 标签解析（向后兼容）。"""
    pattern = r"<problem>(.*?)</problem>"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return [{"content": m.strip()} for m in matches]
    # Fallback：尝试用统一标记解析
    try:
        return parse_unit_markers(text)
    except Exception:
        return []


def _dump_smart_split_raw(raw_text, md_file, label=""):
    """将 LLM 返回的原始标注文本保存到 output/中间产物/{文档名}/ 目录。"""
    try:
        # 从 md_file 中提取文档名（去掉 _raw 后缀 或 直接用 basename）
        if md_file:
            doc_name = Path(md_file).stem
            # 去掉 _raw 后缀
            if doc_name.endswith("_raw"):
                doc_name = doc_name[:-4]
        else:
            doc_name = "未命名文档"
        base_dir = Path("output") / "中间产物" / doc_name
        base_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{label}" if label else ""
        dump_path = base_dir / f"_smart_split_raw{suffix}.md"
    except Exception:
        dump_path = Path("output") / "中间产物" / "_smart_split_raw.md"
        Path("output").mkdir(parents=True, exist_ok=True)

    dump_path.write_text(raw_text or "(空)", encoding='utf-8')
    log(f"   📄 智能分割原始输出已保存: {dump_path}")


def smart_split_with_callable(md_content, llm_callable, md_file=None):
    for attempt in range(2):
        try:
            result_text = llm_callable(md_content, SMART_SPLIT_PROMPT)
        except Exception as e:
            log(f"   ⚠️ 智能分割第 {attempt+1} 次调用失败: {e}")
            continue

        _dump_smart_split_raw(result_text, md_file, label=f"attempt{attempt+1}")

        problems = parse_problem_tags(result_text)
        problems = [p for p in problems if p["content"].strip()]
        if problems:
            log(f"   ✅ 智能分割成功，识别到 {len(problems)} 个题目单元")
            return problems

        log(f"   ⚠️ 第 {attempt+1} 次未识别到有效题目标记")

    log(f"   ⚠️ 智能分割失败，降级为单单元")
    return [{"content": md_content}]


def smart_split(md_content, api_url, api_key, model, md_file=None):
    def _llm_call(text, prompt):
        api_result = call_api(
            api_url, api_key, model,
            text, [], "智能分割",
            prompt, tools=[], max_loops=1,
            max_tokens=SMART_SPLIT_MAX_TOKENS,
        )
        return api_result["content"]

    return smart_split_with_callable(md_content, _llm_call, md_file=md_file)
