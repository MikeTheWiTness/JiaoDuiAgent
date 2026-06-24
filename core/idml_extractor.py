"""IDML 文件提取器 - 从 InDesign IDML 文件提取文本内容为 Markdown。

提取策略：
1. 从 IDML 提取所有 Story 的文本和段落样式
2. 根据段落样式识别标题层级，构建文档结构
3. 按 Story 的起始页面排序，保证内容顺序正确
4. 过滤无用内容（页码、装饰文字等）
"""
import zipfile
import xml.etree.ElementTree as ET
import os
import re
from pathlib import Path


def _get_tag(elem):
    return elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag


def _iter_all(elem):
    yield elem
    for child in elem:
        yield from _iter_all(child)


def _parse_transform(transform_str):
    parts = transform_str.split()
    if len(parts) == 6:
        return float(parts[4]), float(parts[5])
    return 0, 0


def _parse_bounds(bounds_str):
    parts = bounds_str.split()
    if len(parts) == 4:
        return [float(p) for p in parts]
    return [0, 0, 0, 0]


def _extract_stories(z):
    """提取所有 story 的段落内容和样式。"""
    story_files = [n for n in z.namelist()
                   if n.startswith('Stories/Story_') and n.endswith('.xml')]
    story_data = {}

    for sf in story_files:
        story_id = sf.replace('Stories/Story_', '').replace('.xml', '')
        story_xml = z.read(sf)
        story_root = ET.fromstring(story_xml)

        paragraphs = []
        current_chars = []
        current_style = None

        def flush():
            nonlocal current_chars, current_style
            text = ''.join(current_chars).strip()
            if text:
                paragraphs.append({
                    'text': text,
                    'style': current_style
                })
            current_chars = []

        for elem in _iter_all(story_root):
            tag = _get_tag(elem)
            if tag == 'ParagraphStyleRange':
                flush()
                style = elem.get('AppliedParagraphStyle', '')
                current_style = style.split('/')[-1] if '/' in style else style
            elif tag == 'Br':
                current_chars.append('\n')
            elif tag == 'Content' and elem.text:
                current_chars.append(elem.text)

        flush()

        if paragraphs:
            story_data[story_id] = paragraphs

    return story_data


def _get_spread_order(z):
    """从 designmap 获取 spread 顺序。"""
    dm_xml = z.read('designmap.xml')
    dm_root = ET.fromstring(dm_xml)

    spread_files = []
    for elem in _iter_all(dm_root):
        if _get_tag(elem) == 'Spread':
            src = elem.get('src', '')
            if src:
                spread_files.append(src)
    return spread_files


def _get_story_positions(z, spread_files, story_data):
    """获取每个 story 的起始位置（页码和坐标）。"""
    all_tfs = []

    for sf in spread_files:
        sp_xml = z.read(sf)
        sp_root = ET.fromstring(sp_xml)

        pages = []
        for elem in _iter_all(sp_root):
            if _get_tag(elem) == 'Page':
                bounds = _parse_bounds(elem.get('GeometricBounds', ''))
                tx, ty = _parse_transform(elem.get('ItemTransform', ''))
                pages.append({
                    'name': elem.get('Name'),
                    'self': elem.get('Self'),
                    'x': tx,
                    'y': ty,
                    'w': bounds[3] - bounds[1],
                    'h': bounds[2] - bounds[0],
                })

        pages.sort(key=lambda p: p['x'])

        for elem in _iter_all(sp_root):
            if _get_tag(elem) == 'TextFrame':
                story_id = elem.get('ParentStory', '')
                if not story_id or story_id not in story_data:
                    continue

                tf_self = elem.get('Self', '')
                prev_tf = elem.get('PreviousTextFrame', '')
                next_tf = elem.get('NextTextFrame', '')
                tx, ty = _parse_transform(elem.get('ItemTransform', ''))

                page_name = None
                for page in pages:
                    if (page['x'] <= tx < page['x'] + page['w'] and
                            page['y'] <= ty < page['y'] + page['h']):
                        page_name = page['name']
                        break

                if page_name is None and len(pages) >= 2:
                    mid_x = pages[0]['x'] + pages[0]['w']
                    page_name = pages[0]['name'] if tx < mid_x else pages[1]['name']

                if page_name:
                    all_tfs.append({
                        'tf_self': tf_self,
                        'story_id': story_id,
                        'prev_tf': prev_tf,
                        'next_tf': next_tf,
                        'x': tx,
                        'y': ty,
                        'page_name': page_name
                    })

    return all_tfs


def _get_story_start_info(all_tfs):
    """找出每个 story 的第一个 TextFrame（起始位置）。"""
    tf_map = {tf['tf_self']: tf for tf in all_tfs}
    story_start = {}

    for tf in all_tfs:
        story_id = tf['story_id']
        prev = tf['prev_tf']
        if prev == 'n' or prev not in tf_map:
            if story_id not in story_start:
                story_start[story_id] = {
                    'page_name': tf['page_name'],
                    'y': tf['y'],
                    'x': tf['x']
                }

    return story_start


def _page_sort_key(page_name):
    """页面排序键值。有前导零的正文在前，没有的在后。"""
    name = str(page_name)
    m = re.search(r'(\d+)', name)
    if not m:
        return (9999, 9999)
    
    num = int(m.group(1))
    has_leading_zero = name.strip().startswith('0') or (len(m.group(1)) >= 3)
    
    if has_leading_zero:
        return (0, num)
    else:
        return (1, num)


def _is_annotation_style(style):
    """判断是否是批注/旁注类样式。"""
    if not style:
        return False
    annotation_keywords = ['旁注', '小贴士', '贴士', '批注', '注释：']
    return any(k in style for k in annotation_keywords)


def _classify_heading(text, style):
    """根据样式和内容判断标题级别。
    返回 None 表示不是标题，返回 1-6 表示标题级别。
    """
    if not style:
        return None
    
    if _is_annotation_style(style):
        return None
    
    style_lower = style.lower()
    
    if style in ('第一讲', '讲内容'):
        return 1
    if style.startswith('（一）') or style.startswith('(一)'):
        return 2
    if '例文' in style and '标题' in style:
        return 3
    if '标题' in style:
        return 3
    
    return None


def _is_useless(text, style):
    """判断是否是无用内容。"""
    stripped = text.strip()
    if not stripped:
        return True
    
    if len(stripped) <= 3 and re.match(r'^\d+$', stripped):
        return True
    
    if style == 'NormalParagraphStyle' and stripped in (
        '600字', '800字', '500字', '400字', '300字', '200字'
    ):
        return True
    
    if len(stripped) <= 2 and re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩]+$', stripped):
        return True
    
    if style and '标题' in style and len(stripped) <= 2:
        if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩]+$', stripped):
            return True
    
    return False


def _format_paragraph(text, style):
    """将段落格式化为 Markdown。"""
    if not style:
        return text
    
    heading_level = _classify_heading(text, style)
    if heading_level:
        prefix = '#' * (heading_level + 1)
        return f'{prefix} {text}'
    
    if _is_annotation_style(style):
        lines = text.split('\n')
        non_empty = [line.strip() for line in lines if line.strip()]
        if not non_empty:
            return text
        formatted = []
        for i, line in enumerate(non_empty):
            if i == 0:
                formatted.append(f'> 💡 {line}')
            else:
                formatted.append(f'>    {line}')
        return '\n'.join(formatted)
    
    if style in ('注释内容', '出处'):
        lines = text.split('\n')
        return '\n'.join('> ' + line for line in lines)
    
    if '表格' in style and ('宋' in style or '楷' in style or '加粗' in style):
        return f'`{text}`'
    
    return text


def extract_idml_to_markdown(idml_path, output_md_path=None):
    """从 IDML 文件提取文本并生成 Markdown。
    
    Args:
        idml_path: IDML 文件路径
        output_md_path: 输出 Markdown 文件路径（可选）
    
    Returns:
        dict: 包含 markdown 文本、页数、段落数等信息
    """
    idml_path = str(idml_path)
    if not os.path.exists(idml_path):
        raise FileNotFoundError(f"IDML 文件不存在: {idml_path}")

    with zipfile.ZipFile(idml_path) as z:
        story_data = _extract_stories(z)
        spread_files = _get_spread_order(z)
        all_tfs = _get_story_positions(z, spread_files, story_data)
        story_start = _get_story_start_info(all_tfs)

    sorted_stories = sorted(
        story_start.items(),
        key=lambda item: (
            _page_sort_key(item[1]['page_name']),
            item[1]['y'],
            item[1]['x']
        )
    )

    md_lines = []
    base_name = Path(idml_path).stem
    md_lines.append(f"# {base_name}")
    md_lines.append("")

    total_paras = 0
    pages_with_content = set()

    for story_id, start_info in sorted_stories:
        paras = story_data.get(story_id, [])
        page = start_info['page_name']
        pages_with_content.add(page)

        for para in paras:
            text = para['text']
            style = para['style']

            if _is_useless(text, style):
                continue

            md_text = _format_paragraph(text, style)
            md_lines.append(md_text)
            md_lines.append("")
            total_paras += 1

    if output_md_path:
        output_md_path = str(output_md_path)
        os.makedirs(os.path.dirname(output_md_path), exist_ok=True)
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))

    return {
        'markdown': '\n'.join(md_lines),
        'page_count': len(pages_with_content),
        'paragraph_count': total_paras,
        'story_count': len(story_data),
    }
