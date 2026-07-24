"""创建 GitHub Issues - 高中语文 v2.0 切片"""
import subprocess
import time

import requests

REPO = "MikeTheWiTness/JiaoDuiAgent"
API_BASE = "https://api.github.com/repos"

# 从 gh CLI 获取 token
def get_token():
    result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
    return result.stdout.strip()

TOKEN = get_token()
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json",
}

def create_issue(title, body):
    url = f"{API_BASE}/{REPO}/issues"
    data = {"title": title, "body": body}
    resp = requests.post(url, headers=HEADERS, json=data)
    if resp.status_code == 201:
        issue = resp.json()
        print(f"✅ 创建成功: #{issue['number']} {title}")
        return issue["number"]
    else:
        print(f"❌ 创建失败: {resp.status_code} {resp.text[:200]}")
        return None

# 先把之前的乱码 issue #2 关了
def close_issue(num):
    url = f"{API_BASE}/{REPO}/issues/{num}"
    data = {"state": "closed"}
    resp = requests.patch(url, headers=HEADERS, json=data)
    if resp.status_code == 200:
        print(f"✅ 已关闭 #{num}")
    else:
        print(f"❌ 关闭失败 #{num}: {resp.status_code}")

close_issue(1)  # 测试 Issue
close_issue(2)  # 乱码 Issue

time.sleep(1)

# Issue 列表（按依赖顺序，无依赖的先创建）
issues = [
    {
        "title": "[v2.0][高中语文] 切片1：基础修复 + 框架对齐",
        "body": """## What to build

修复高中语文 的接口不兼容问题，将 subject.py 对齐到高中物理 v3.0 的规范，版本号升级到 v2.0。

具体内容：
- 修复 split_lecture / split_exam / generate_knowledge / proofread_one 等方法签名，与 core/defaults.py 和 DefaultApp 调用方式一致
- get_tool_instructions 改为无参数调用，在 get_question_prompt / get_knowledge_prompt 中拼接工具说明
- 版本号升级到 v3.0
- 清理 app.py 中的路径 hack
- 修复后程序能正常启动并跑通基础流程

## Acceptance criteria

- [ ] 启动高中语文程序不报错
- [ ] 讲义模式 Word 转 MD + 拆分流程正常
- [ ] 试卷模式 Word 转 MD + 拆分流程正常
- [ ] 校对流程能正常调用 API
- [ ] 版本号显示为 v2.0

## Blocked by

None - can start immediately
""",
        "blocked_by": [],
    },
    {
        "title": "[v2.0][高中语文] 切片2：识典古籍适配 + WebFetchTool 接入",
        "body": """## What to build

给 WebFetchTool 增加识典古籍（shidianguji.com）的专门适配，并将 WebFetchTool 加入高中语文的工具集。

具体内容：
- 新增 _fetch_shidianguji 方法：识典古籍搜索结果页解析 + 详情页原文提取
- 自动识别识典古籍 URL，使用专用抓取逻辑
- WebFetchTool 的 description 更新识典古籍相关说明
- 将 WebFetchTool 加入高中语文 build_tools()
- 确保 web_search + web_fetch 的组合使用正常

## Acceptance criteria

- [ ] WebFetchTool 能正确识别识典古籍 URL 并使用专用适配
- [ ] 识典古籍搜索能返回搜索结果列表
- [ ] 识典古籍详情页能提取完整原文
- [ ] 高中语文工具集同时包含 WebSearchTool 和 WebFetchTool
- [ ] 搜索失败/超时的降级处理正常

## Blocked by

None - can start immediately
""",
        "blocked_by": [],
    },
    {
        "title": "[v2.0][高中语文] 切片3：人工标记分割",
        "body": """## What to build

新增人工标记分割功能，支持用户在 Word/MD 文件中用成对标记手动指定题目边界。

具体内容：
- 识别 `###### 题目开始 ######` 和 `###### 题目结束 ######` 成对标记
- 校验标记配对，不配对时报错提示用户
- 未被标记的内容自动丢弃（引言、说明等）
- 分割结果格式与现有 default_split_lecture 输出兼容
- 全模式可用（讲义/试卷/自由校对/批注评审）

## Acceptance criteria

- [ ] 正常成对标记能正确分割
- [ ] 标记不配对时抛出明确的错误信息
- [ ] 无标记时抛出错误（不自动降级）
- [ ] 多段标记分割正确
- [ ] 标记前后的垃圾内容被正确丢弃
- [ ] 分割结果可直接用于后续校对流程

## Blocked by

None - can start immediately
""",
        "blocked_by": [],
    },
    {
        "title": "[v2.0][高中语文] 切片4：智能分割（LLM + XML 标记）",
        "body": """## What to build

新增智能分割功能，调用 LLM 自动识别文档中的完整题目单元，用 `<problem></problem>` 标记边界。

具体内容：
- 新增 smart_split 模块
- 调用 LLM 在原文中插入 `<problem></problem>` 标记（不修改原文任何内容）
- 解析 XML 标记，提取每个题目单元的内容
- 失败重试 1 次
- 再次失败则降级为单单元（全文作为一个校对单元）
- 输出格式与现有拆分结果兼容
- 预留独立测试接口

## Acceptance criteria

- [ ] `<problem>` 标记解析正确
- [ ] 标记内容与原文完全一致（无篡改）
- [ ] 失败重试机制正常工作
- [ ] 降级逻辑正常（两次失败后返回单单元）
- [ ] 空文档/无标记等边界情况处理正常
- [ ] 分割结果可直接用于后续校对流程

## Blocked by

None - can start immediately
""",
        "blocked_by": [],
    },
    {
        "title": "[v2.0][高中语文] 切片5：Word 批注提取",
        "body": """## What to build

新增 Word 批注提取功能，从带批注的 .docx 文件中提取批注内容，插入到原文对应位置。

具体内容：
- 从 docx 的 comments.xml 中提取所有批注（作者、内容、ID）
- 找到批注在正文中的引用位置
- 将批注以 `[📝批注N：内容]` 形式插入原文对应位置
- 输出带批注标记的 Markdown 文件
- 无批注文件的处理（正常转换，提示无批注）
- 预留独立测试接口

## Acceptance criteria

- [ ] 能正确提取 docx 中的所有批注
- [ ] 批注能插入到原文正确位置
- [ ] 批注格式清晰，不影响原文阅读
- [ ] 无批注文件处理正常
- [ ] 多条批注按顺序编号
- [ ] 输出的 md 文件可用于后续校对流程

## Blocked by

None - can start immediately
""",
        "blocked_by": [],
    },
    {
        "title": "[v2.0][高中语文] 切片6：文言文/诗歌识别 + 前置搜索 + 自动 diff",
        "body": """## What to build

新增 chinese_classics_tools 模块，实现文言文/诗歌三层校对架构的前两层：类型识别 + 前置原文搜索 + 自动差异比对。

具体内容：
- 文本类型识别：文言文（虚词密度）、诗歌（句式整齐度）、现代文
- 前置原文搜索：文言文→识典古籍，诗歌→搜韵网，提取前几句作为搜索关键词
- 自动差异比对：字符级 diff，输出差异列表（位置、原文、待校、差异描述）
- 生成前置参考原文段落，附加在校对内容前送给 LLM
- 每个函数都可独立调用和测试
- 搜索失败不影响后续流程（LLM 可自行补搜）

## Acceptance criteria

- [ ] 文言文识别准确率达到 80% 以上（多篇典型文本测试）
- [ ] 诗歌识别准确率达到 80% 以上
- [ ] 现代文不会被误识别为文言文/诗歌
- [ ] 前置搜索能正确获取原文
- [ ] 自动 diff 能找出所有字面差异（增、删、改）
- [ ] 搜索失败时优雅降级，不报错阻断
- [ ] 前置参考段落格式清晰，LLM 能正确理解

## Blocked by

- #2 （切片2：识典古籍适配）
""",
        "blocked_by": [2],
    },
    {
        "title": "[v2.0][高中语文] 切片7：四种分割方式接入业务层",
        "body": """## What to build

在 subject.py 中接入四种分割方式，让用户可选择：不拆分 / 普通规则分割 / 智能分割 / 人工标记分割。

具体内容：
- 新增 split_mode 配置项（none / rule / smart / manual）
- split_lecture 和 split_exam 支持四种分割方式
- 智能分割需要调用 API，传入 API 配置
- 人工标记分割的错误处理
- 与现有输出目录结构兼容
- get_ui_features 中暴露分割方式选项

## Acceptance criteria

- [ ] 不拆分模式：整份内容作为一个校对单元
- [ ] 普通规则分割：与现有行为一致
- [ ] 智能分割：调用 LLM 分割，结果正确
- [ ] 人工标记分割：按标记分割，错误提示清晰
- [ ] 四种方式输出目录结构一致
- [ ] 分割方式可通过 UI 选择

## Blocked by

- #3 （切片3：人工标记分割）
- #4 （切片4：智能分割）
- #1 （切片1：基础修复）
""",
        "blocked_by": [1, 3, 4],
    },
    {
        "title": "[v2.0][高中语文] 切片8：自由校对模式 UI + 业务",
        "body": """## What to build

新增自由校对模式，支持粘贴文本+上传图片/文件，灵活选择分割方式。

具体内容：
- source_mode 新增"自由校对"选项（讲义/试卷/自由校对/批注评审）
- 自由校对模式下显示：文本输入框 + 图片上传按钮 + 添加文件按钮
- 粘贴内容临时存为 md + images 文件夹
- 支持四种分割方式
- 走现有校对流程（生成报告、生成 PDF）
- 输出目录名：`自由校对_时间戳`
- 模式切换时动态显隐对应控件

## Acceptance criteria

- [ ] 自由校对模式能在 UI 中切换
- [ ] 粘贴文本 + 上传图片后能生成临时 md 文件
- [ ] 上传 Word/MD 文件能正常转换
- [ ] 四种分割方式都能正常工作
- [ ] 校对流程正常，生成 PDF 报告
- [ ] 输出目录结构正确
- [ ] 切换模式时 UI 控件显隐正确

## Blocked by

- #1 （切片1：基础修复）
- #7 （切片7：四种分割方式接入业务层）
""",
        "blocked_by": [1, 7],
    },
    {
        "title": "[v2.0][高中语文] 切片9：批注评审模式 UI + 业务",
        "body": """## What to build

新增批注评审模式，支持带批注的 Word 文档，LLM 评判已有批注并补充发现遗漏错误。

具体内容：
- source_mode 新增"批注评审"选项
- 接入 Word 批注提取功能（切片5）
- 新增批注评审专用提示词
- 批注评审数据结构定义（与后续 PDF 生成兼容）
- 支持四种分割方式
- 输出专用的批注评审结果格式

## Acceptance criteria

- [ ] 批注评审模式能在 UI 中切换
- [ ] 带批注的 Word 文档能正确提取批注
- [ ] LLM 能正确评判每条批注（正确/有误/部分正确）
- [ ] LLM 能补充发现遗漏的错误
- [ ] 输出格式包含：原文 + 逐条评审 + 补充发现
- [ ] 四种分割方式都能正常工作
- [ ] 有答案时校对答案，无答案时专注题干

## Blocked by

- #5 （切片5：Word 批注提取）
- #7 （切片7：四种分割方式接入业务层）
- #8 （切片8：自由校对模式）
""",
        "blocked_by": [5, 7, 8],
    },
    {
        "title": "[v2.0][高中语文] 切片10：批注评审 PDF 生成（逐条展开式）",
        "body": """## What to build

新增批注评审模式的 PDF 生成，采用逐条展开式排版。

具体内容：
- 新增 build_comment_review_content 函数
- 排版结构：原文完整展示（带批注位置标记）→ 逐条评审 → 补充发现
- 每条评审包含：原批注内容 + 评判结果（✅正确/❌有误/⚠️部分正确）+ 评判理由
- 补充发现按正常校对标记格式
- 与现有 generate_combined_pdf 流程集成
- LaTeX 模板复用现有基础模板，新增评审专用命令

## Acceptance criteria

- [ ] 批注评审 PDF 能成功编译生成
- [ ] 原文展示完整，批注位置有编号标记
- [ ] 逐条评审排版清晰，评判结果醒目
- [ ] 补充发现格式与正常校对一致
- [ ] 多题目时分页正确
- [ ] 图片能正常显示

## Blocked by

- #9 （切片9：批注评审模式）
""",
        "blocked_by": [9],
    },
    {
        "title": "[v2.0][高中语文] 切片11：提示词优化 + 通用功能完善",
        "body": """## What to build

更新所有提示词，完善通用功能。

具体内容：
- 更新题目校对提示词：加入工具使用说明、三层架构说明、有答案校答案/无答案校题干
- 更新知识校对提示词：加入工具使用说明
- 新增智能分割提示词
- 新增批注评审提示词
- 工具调用说明更新（识典古籍、搜韵网的使用说明）
- 前置搜索 + 自动 diff 的结果如何呈现给 LLM

## Acceptance criteria

- [ ] 题目校对提示词包含完整的工具使用说明
- [ ] 提示词明确说明"有答案校答案，无答案校题干"
- [ ] 智能分割提示词能让 LLM 正确输出 `<problem>` 标记
- [ ] 批注评审提示词清晰说明评审标准和输出格式
- [ ] 工具说明清晰描述了识典古籍和搜韵网的使用场景
- [ ] 前置搜索结果和 diff 列表能被 LLM 正确理解和使用

## Blocked by

- #6 （切片6：文言文/诗歌识别 + 前置搜索 + 自动 diff）
- #7 （切片7：四种分割方式接入业务层）
""",
        "blocked_by": [6, 7],
    },
    {
        "title": "[v2.0][高中语文] 切片12：GUI 完善 + 整体联调",
        "body": """## What to build

完善 GUI 界面，进行整体联调，确保所有模式和功能正常工作。

具体内容：
- 四种 source mode 完整 UI 切换
- 分割方式下拉选择（不拆分/普通规则/智能分割/人工标记）
- 自由校对模式的文本输入区和图片上传按钮
- 批注评审模式的 UI 适配
- 动态显隐逻辑完善
- 四种模式端到端流程跑通
- 日志和错误提示友好
- 整体用户体验优化

## Acceptance criteria

- [ ] 讲义模式完整流程正常（转换→拆分→校对→PDF）
- [ ] 试卷模式完整流程正常
- [ ] 自由校对模式完整流程正常（粘贴/上传→校对→PDF）
- [ ] 批注评审模式完整流程正常（上传带批注文档→评审→PDF）
- [ ] 四种分割方式在各模式下都能正常切换
- [ ] UI 切换流畅，无控件残留或错位
- [ ] 错误提示清晰友好
- [ ] 版本号显示为 v2.0

## Blocked by

- #8 （切片8：自由校对模式）
- #9 （切片9：批注评审模式）
- #10 （切片10：批注评审 PDF）
- #11 （切片11：提示词优化）
""",
        "blocked_by": [8, 9, 10, 11],
    },
]

# 按顺序创建，记录编号映射
issue_map = {}
for i, issue in enumerate(issues):
    # 更新 blocked_by 中的编号（用已创建的真实编号替换）
    body = issue["body"]
    for old_num, new_num in issue_map.items():
        body = body.replace(f"#{old_num} ", f"#{new_num} ")
        body = body.replace(f"- #{old_num}", f"- #{new_num}")

    num = create_issue(issue["title"], body)
    if num:
        issue_map[i + 1] = num  # i+1 是切片编号
    time.sleep(0.5)  # 避免 rate limit

print()
print("=== Issue 编号映射 ===")
for slice_num, issue_num in issue_map.items():
    print(f"切片{slice_num} → Issue #{issue_num}")
