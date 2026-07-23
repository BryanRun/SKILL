import importlib.util
import json
import unittest
from pathlib import Path


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", "_under_test"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class BrandingFooterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checklist = load_script("gerrit_post_checklist.py")
        cls.review = load_script("gerrit_post_review.py")
        skill_json = Path(__file__).resolve().parents[1] / "skill.json"
        cls.footer = "Powered by gerrit-pipeline v%s" % json.loads(skill_json.read_text(encoding="utf-8"))["version"]

    def test_checklist_footer_uses_skill_version(self):
        branded = self.checklist._append_branding_footer("### Checklist\n- [x] item\n")

        self.assertTrue(branded.endswith("\n---\n\n%s\n" % self.footer))

    def test_review_footer_uses_skill_version(self):
        branded = self.review._append_branding_footer("## Review\nsuggested_score: +1\n")

        self.assertTrue(branded.endswith("\n---\n\n%s\n" % self.footer))

    def test_footer_is_not_duplicated(self):
        text = "body\n\n---\n\n%s\n" % self.footer

        branded = self.review._append_branding_footer(text)

        self.assertEqual(branded.count(self.footer), 1)
        self.assertTrue(branded.endswith("\n---\n\n%s\n" % self.footer))

    def test_old_footer_is_replaced(self):
        text = "body\n\nPowered by gerrit-pipeline v0.0.1\n"

        branded = self.checklist._append_branding_footer(text)

        self.assertNotIn("Powered by gerrit-pipeline v0.0.1", branded)
        self.assertEqual(branded.count(self.footer), 1)
        self.assertTrue(branded.endswith("\n---\n\n%s\n" % self.footer))


if __name__ == "__main__":
    unittest.main()
