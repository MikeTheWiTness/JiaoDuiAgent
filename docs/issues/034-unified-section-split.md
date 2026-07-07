# Issue 034：规则拆分统一 —— section 模式核心

**关联 ADR**：[ADR-0017](../adr/0017-unified-section-split.md)（决策1/2/4/7/8/10）

---

## What to build

将所有学科的讲义规则拆分统一为 section 模式，包含以下改造：

### 1. 默认 section 模式 + 通用 pattern

- `default_split_lecture` 的 `split_mode` 默认值 → `"section"`
- 新增 `DEFAULT_SECTION_PATTERN` 常量：
  ```
  ^#{2,3}\s                    # ## / ### 标题
  |\*\*(例|练|变式|真题)\d+\*\*  # **例1** 等
  |\*\*教师版\*\*               # **教师版**
  |必备知识|模型大招|重难点突破   # 通用知识标题
  ```
- 学科可通过 `section_pattern_extensions` 追加关键词

### 2. 命名统一为 `单元N`

- section 模式输出目录从 `板块N` → `单元N`
- 和 ADR-0017 的手动标记统一（`###### 单元开始/结束 ######`）呼应

### 3. 装饰图片清除统一

- `strip_decor_images_from_file(md_file)` 提升到 `default_split_lecture` 开头
- 各学科 `split_lecture` 中移除重复调用

### 4. 两级拆分：板块内例题提取

- 一级边界（`##`/`###`）切出大板块
- 二级提取：板块内匹配 `wrapped_patterns` 的例题行（`**例1**`、`**教师版**`、`**练1**` 等）剥离为独立单元
- 无标记的内联题留在知识单元内
- 连续编号：知识单元和题目单元统一编为 `单元N`

### 5. 连续标题合并

- 当多个一级边界连续出现、中间无实质内容时，合并为一个单元
- 消除 `## 模块N` 紧接 `### 必备知识` 产生的空壳单元

### 6. 学科 config 更新

- 9 个学科的 `config.json`：`split_mode` → `"section"`，`section_pattern_extensions` → `[]`
- 高中历史保持原样（已有成熟 section 配置）
- `config_schema.py` / `config_loader.py` 适配新默认值

## Acceptance criteria

- [ ] 物理讲义（直线运动）拆分正确：导航区 + 知识单元 + 例题单元交替
- [ ] 化学讲义（化学键）拆分正确：9 个单元，无空壳
- [ ] 语文讲义（虚词）拆分正确：知识单元 + 小试牛刀/例题单元交替
- [ ] `单元N/` 命名一致（不出现 `第N题`、`板块N`、`知识`）
- [ ] 装饰图片在拆分前被清除
- [ ] 例题（`**例1**`等）独立成单元，内联题留在知识单元
- [ ] 连续标题（`##`+`###`）合并为一个单元
- [ ] 9 个学科 config 更新后拆分正常
- [ ] 单元测试覆盖：section 拆分、例题提取、标题合并

## Blocked by

- Issue 033（`parse_unit_markers` 共用解析器可用于验证）
