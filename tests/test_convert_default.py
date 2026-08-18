"""M1 回归：默认 Word 转换必须完成 pandoc → normalize_caret_tilde → 格式增强。

修复前 6 个学科没有 convert_file_to_md，UI 直连 convert_with_pandoc 后只做
enhance，不执行 normalize_caret_tilde，导致 ^x^/~x~ 原样进入拆分与校对内容；
小学语文则因 UI 又重复 enhance 一次。
"""
import pytest

from core.defaults import default_convert_file_to_md


@pytest.fixture
def word_path(tmp_path):
    p = tmp_path / "讲义.docx"
    p.write_bytes(b"fake docx")
    return str(p)


def test_default_word_conversion_normalizes_caret_tilde(word_path, tmp_path, monkeypatch):
    output_md = str(tmp_path / "out.md")
    img_dir = str(tmp_path / "images")

    monkeypatch.setattr("core.pandoc_utils.check_pandoc", lambda: True)

    def fake_convert(input_path, out_md, imgs, use_mathjax=False):
        with open(out_md, "w", encoding="utf-8") as f:
            f.write("v^2^ + H~2~O")
        return True

    enhance_calls = []
    monkeypatch.setattr("core.pandoc_utils.convert_with_pandoc", fake_convert)
    monkeypatch.setattr(
        "core.pandoc_utils.enhance_docx_conversion",
        lambda docx, md: enhance_calls.append(md),
    )

    result = default_convert_file_to_md(word_path, output_md, img_dir, use_mathjax=False)

    assert result["success"] is True
    with open(output_md, encoding="utf-8") as f:
        text = f.read()
    assert "v<上标>2</上标> + H<下标>2</下标>O" in text
    assert enhance_calls == [output_md], "默认转换应只增强一次"
