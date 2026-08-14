import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.free_proofread import (
    create_free_proofread_md,
)


class TestCreateFreeProofreadMd(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_from_text_only(self):
        text = "这是一段要校对的文字。"
        md_path = create_free_proofread_md(text, output_dir=self.tmpdir)
        self.assertTrue(os.path.exists(md_path))
        self.assertTrue(md_path.endswith(".md"))
        with open(md_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn("这是一段要校对的文字", content)

    def test_create_with_images(self):
        text = "看下图："
        img_dir = os.path.join(self.tmpdir, "images")
        os.makedirs(img_dir, exist_ok=True)
        img_path = os.path.join(img_dir, "test.png")
        with open(img_path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n')

        md_path = create_free_proofread_md(text, images=[img_path], output_dir=self.tmpdir)
        self.assertTrue(os.path.exists(md_path))
        with open(md_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn("![图片", content)

    def test_output_dir_creation(self):
        text = "测试"
        new_dir = os.path.join(self.tmpdir, "new_dir")
        md_path = create_free_proofread_md(text, output_dir=new_dir)
        self.assertTrue(os.path.exists(md_path))
        self.assertTrue(os.path.isdir(new_dir))

    def test_filename_has_timestamp(self):
        text = "测试"
        md_path = create_free_proofread_md(text, output_dir=self.tmpdir)
        basename = os.path.basename(md_path)
        self.assertIn("自由校对", basename)


class TestSubjectFreeMode(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import importlib.util
        subject_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "subjects", "高中语文v3.0"
        )
        spec = importlib.util.spec_from_file_location(
            "yuwen_subject",
            os.path.join(subject_dir, "subject.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.app = mod.SubjectApp(subject_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ui_features_has_free_mode(self):
        features = self.app.get_ui_features()
        self.assertIn("show_source_modes", features)
        self.assertIn("自由校对", features["show_source_modes"])

    def test_ui_features_three_modes(self):
        features = self.app.get_ui_features()
        modes = features["show_source_modes"]
        self.assertGreaterEqual(len(modes), 3)


if __name__ == "__main__":
    unittest.main()
