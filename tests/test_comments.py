import zipfile
import re
import os
import unittest

path = r'C:\Users\witne\Desktop\校对临时\高中语文教研实习生笔试试卷(1).docx'


class TestCommentsInspection(unittest.TestCase):
    """探查指定 docx 的正文段落与批注结构。

    依赖本机硬编码文件，文件不存在时跳过，避免拖垮测试套件导入。
    """

    def test_inspect_docx_comments(self):
        if not os.path.exists(path):
            self.skipTest(f"探查目标文件不存在: {path}")
        print('文件存在: True')
        print('文件大小:', os.path.getsize(path), 'bytes')

        with zipfile.ZipFile(path, 'r') as z:
            names = z.namelist()
            print()
            print('=== 内部文件 ===')
            for n in names:
                print(' ', n)

            # 读文档正文
            if 'word/document.xml' in names:
                content = z.read('word/document.xml').decode('utf-8')
                # 提取段落文本
                paragraphs = re.findall(r'<w:p[^>]*>(.*?)</w:p>', content, re.DOTALL)
                print()
                print(f'=== 段落数: {len(paragraphs)} ===')
                print()
                print('=== 前30个段落 ===')
                for i, p in enumerate(paragraphs[:30]):
                    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p)
                    text = ''.join(texts).strip()
                    if text:
                        print(f'[{i}] {text[:120]}')

            # 检查批注
            comments_files = [n for n in names if 'comment' in n.lower()]
            print()
            print('=== 批注相关文件 ===')
            for n in comments_files:
                print(' ', n)

            if 'word/comments.xml' in names:
                comments_content = z.read('word/comments.xml').decode('utf-8')
                # 提取所有批注
                comment_blocks = re.findall(r'<w:comment[^>]*>(.*?)</w:comment>', comments_content, re.DOTALL)
                print()
                print(f'=== 批注数: {len(comment_blocks)} ===')
                print()
                print('=== 前10条批注 ===')
                for i, c in enumerate(comment_blocks[:10]):
                    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', c)
                    text = ''.join(texts).strip()
                    author = re.search(r'w:author="([^"]*)"', c)
                    print(f'[{i}] 作者:{author.group(1) if author else "?"} 内容:{text[:150]}')

            # 看看正文里怎么引用批注
            if 'word/document.xml' in names:
                content = z.read('word/document.xml').decode('utf-8')
                comment_refs = re.findall(r'<w:commentReference[^>]*/>', content)
                print()
                print(f'=== 正文批注引用数: {len(comment_refs)} ===')

                # 找批注前后的上下文
                print()
                print('=== 批注位置上下文（前5个） ===')
                # 找 commentReference 前后的文字
                for i, m in enumerate(re.finditer(r'<w:commentReference[^>]*/>', content)):
                    if i >= 5:
                        break
                    start = max(0, m.start() - 200)
                    end = min(len(content), m.end() + 200)
                    context = content[start:end]
                    # 提取文本
                    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', context)
                    text = ''.join(texts)
                    print(f'[{i}] ...{text.strip()[:100]}...')


if __name__ == "__main__":
    unittest.main()
