"""测试 difflib 节选精确截取算法（ADR 0004 决策 2 + Issue #4）"""
import unittest
import sys, os, re, difflib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.chinese_classics_tools import extract_excerpt_from_full


class TestExcerptExtraction(unittest.TestCase):

    def setUp(self):
        # 含家世背景和完整传记的韦凑传
        self.weicou_full = (
            "韦凑字彦宗，京兆万年人。祖叔谐，贞观中为库部郎中，"
            "与弟吏部郎中叔谦、兄主爵郎中季武同省，时号三列宿。"
            "凑，永淳初，解褐婺州参军事，徙资州司兵。观察使房昶才之，"
            "表于朝，迁扬州法曹。州人孟神爽罢仁寿令，豪纵数犯法，"
            "交通贵戚，吏莫敢绳。凑按治，杖杀之，远近称伏。"
            "入为相王府属。时姚崇兼府长史，尝曰：韦子识远文详，吾恨晚得之。"
            "六迁司农少卿，忤宗楚客，出为贝州刺史。睿宗立，"
            "授鸿胪少卿，徙太府，兼通事舍人。时改葬故太子重俊，有诏加谥。"
            "又诏雪李多祚等罪，议赠官。凑上言：王者发号出令，必法天道。"
            "景云初，作金仙等观，凑谏，以为：方农月兴功，虽赀出公主。"
            "不听。凑执争，以万物生育，草木昆蚑伤伐甚多，非仁圣本意。"
            "出为陜、汝、岐三州刺史。开元初，欲建碑靖陵，凑以古园陵不立碑。"
            "迁右卫大将军。寻徙河南尹，封彭城郡公。"
            "会洛阳主簿王钧以赇抵死，出凑曹州刺史。"
            "卒，年六十五，赠幽州都督，谥曰文。子见素。"
        )
        self.weicou_excerpt = (
            "韦凑字彦宗，京兆万年人。永淳初，解褐婺州参军事。"
            "徙资州司兵，观察使房昶才之，表于朝，迁扬州法曹。"
            "卒，年六十五。"
        )

    def norm(self, s):
        return re.sub(r'[^一-鿿]', '', s)

    def test_excerpt_covers_all_hanzi(self):
        """截取结果包含节选的全部汉字（可多不可少）"""
        result = extract_excerpt_from_full(self.weicou_full, self.weicou_excerpt, margin=0)
        self.assertIsNotNone(result)
        n_result = self.norm(result)
        n_excerpt = self.norm(self.weicou_excerpt)
        missing = set(n_excerpt) - set(n_result)
        self.assertEqual(missing, set(),
                         f"截取结果缺少节选的汉字: {missing}")

    def test_identical_text_same_length(self):
        """节选=全文时 margin=0 返回内容等长"""
        text = "学而时习之，不亦说乎。"
        result = extract_excerpt_from_full(text, text, margin=0)
        self.assertIsNotNone(result)
        # 去标点汉字数相等
        self.assertEqual(len(self.norm(result)), len(self.norm(text)))

    def test_margin_adds_context(self):
        """margin > 0 结果不短于 margin=0"""
        r0 = extract_excerpt_from_full(self.weicou_full, self.weicou_excerpt, margin=0)
        r20 = extract_excerpt_from_full(self.weicou_full, self.weicou_excerpt, margin=20)
        self.assertIsNotNone(r0); self.assertIsNotNone(r20)
        self.assertGreaterEqual(len(r20), len(r0))

    def test_empty_inputs_return_none(self):
        self.assertIsNone(extract_excerpt_from_full("", "test"))
        self.assertIsNone(extract_excerpt_from_full("test", ""))
        self.assertIsNone(extract_excerpt_from_full("", ""))

    def test_no_match_returns_none(self):
        result = extract_excerpt_from_full("abcdefg", "一二三四五六七八九十")
        self.assertIsNone(result)

    def test_margin_does_not_exceed_full(self):
        short = "韦凑字彦宗"
        result = extract_excerpt_from_full(self.weicou_full, short, margin=10000)
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), len(self.weicou_full))


if __name__ == "__main__":
    unittest.main()
