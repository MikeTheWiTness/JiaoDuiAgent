"""EditFileTool 单元测试 —— 搜索替换文件工具。"""
from shared.bash_tool import EditFileTool


class TestEditFileTool:
    """测试 EditFileTool 的核心行为。"""

    def test_replace_single_occurrence(self, temp_dir):
        file_path = temp_dir / "test.md"
        file_path.write_text("小明去了北京。", encoding="utf-8")
        tool = EditFileTool()
        result = tool._run(path=str(file_path), old_string="北京", new_string="上海")
        content = file_path.read_text(encoding="utf-8")
        assert "上海" in content
        assert "北京" not in content
        assert "替换成功" in result

    def test_replace_with_preview(self, temp_dir):
        file_path = temp_dir / "test.md"
        file_path.write_text("第一行\n小明去了北京。\n第三行\n", encoding="utf-8")
        tool = EditFileTool()
        result = tool._run(path=str(file_path), old_string="北京", new_string="上海")
        # 预览应包含前后行
        assert "第一行" in result or "第三行" in result

    def test_not_found_returns_error(self, temp_dir):
        file_path = temp_dir / "test.md"
        file_path.write_text("小明去了北京。", encoding="utf-8")
        tool = EditFileTool()
        result = tool._run(path=str(file_path), old_string="南京", new_string="上海")
        assert "未找到" in result or "找不到" in result
        # 文件内容应不变
        content = file_path.read_text(encoding="utf-8")
        assert "北京" in content

    def test_not_found_suggests_context(self, temp_dir):
        file_path = temp_dir / "test.md"
        file_path.write_text("一行\n小明去了北京。\n三行\n", encoding="utf-8")
        tool = EditFileTool()
        result = tool._run(path=str(file_path), old_string="南京", new_string="上海")
        # 错误信息应提示文件行数或上下文
        assert ("3" in result) or ("行" in result) or ("小明" in result)

    def test_empty_old_string(self, temp_dir):
        file_path = temp_dir / "test.md"
        file_path.write_text("测试内容", encoding="utf-8")
        tool = EditFileTool()
        result = tool._run(path=str(file_path), old_string="", new_string="替换")
        assert "错误" in result or "不能为空" in result

    def test_file_not_found(self, temp_dir):
        tool = EditFileTool()
        result = tool._run(path=str(temp_dir / "不存在.md"), old_string="x", new_string="y")
        assert "失败" in result or "错误" in result or "不存在" in result

    def test_first_occurrence_only(self, temp_dir):
        """多出现时只替换第一个匹配。"""
        file_path = temp_dir / "test.md"
        file_path.write_text("北京 北京 北京", encoding="utf-8")
        tool = EditFileTool()
        tool._run(path=str(file_path), old_string="北京", new_string="上海")
        content = file_path.read_text(encoding="utf-8")
        # 第一个北京被替换，后面两个保留
        assert content == "上海 北京 北京"

    def test_utf8_content_preserved(self, temp_dir):
        file_path = temp_dir / "test.md"
        original = "中文内容、日本語、한국어、😀"
        file_path.write_text(original, encoding="utf-8")
        tool = EditFileTool()
        tool._run(path=str(file_path), old_string="😀", new_string="🎉")
        content = file_path.read_text(encoding="utf-8")
        assert "🎉" in content
        assert "😀" not in content
        assert "日本語" in content  # 其余内容不受影响

    def test_multiline_content(self, temp_dir):
        file_path = temp_dir / "test.md"
        file_path.write_text("第一行\n第二行\n第三行\n", encoding="utf-8")
        tool = EditFileTool()
        tool._run(path=str(file_path), old_string="第二行", new_string="替换行")
        content = file_path.read_text(encoding="utf-8")
        assert "替换行" in content
        assert "第二行" not in content
        assert "第一行" in content
        assert "第三行" in content


class TestEditFileToolToolSchema:
    """测试工具 Schema 定义。"""

    def test_tool_name(self):
        tool = EditFileTool()
        assert tool.name == "edit_file"

    def test_args_schema_fields(self):
        tool = EditFileTool()
        schema = tool.args_schema.model_json_schema()
        props = schema["properties"]
        assert "path" in props
        assert "old_string" in props
        assert "new_string" in props
        assert "path" in schema.get("required", [])
        assert "old_string" in schema.get("required", [])
        assert "new_string" in schema.get("required", [])
