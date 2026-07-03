import importlib.util
import unittest
from pathlib import Path


VALID_MESSAGE = """【bug】【CHYT1V-1058】修复仪表双闪提示音异常

【原因分析】双闪状态变化未触发提示音播放逻辑
【解决方案】补充状态监听后触发提示音播放流程
【自测用例】开启双闪后观察仪表提示音播放且关闭后声音停止
【自测方法】本地手动验证三次
【影响范围】仪表双闪提示音相关流程
【代码修改量】约十行
【提交项目/分支】al_chery-d01_dev2
【体现版本】After 2026/7/2
Change-Id: I1234567890abcdef
"""


class CommitMsgGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts" / "commit_msg_guard.py"
        spec = importlib.util.spec_from_file_location("commit_msg_guard_under_test", path)
        cls.guard = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(cls.guard)

    def test_lint_accepts_valid_message(self):
        self.assertEqual(self.guard.lint_message(VALID_MESSAGE), [])

    def test_lint_rejects_forbidden_trailers(self):
        message = VALID_MESSAGE + "Co-authored-by: Cursor <cursor@example.com>\nMade-with: Cursor\n"

        errors = self.guard.lint_message(message)

        self.assertTrue(any("禁止的模板外 trailer" in error for error in errors))

    def test_sanitize_removes_known_forbidden_trailers(self):
        message = (
            VALID_MESSAGE
            + "Co-authored-by: Cursor <cursor@example.com>\n"
            + "Signed-off-by: Cursor <cursor@example.com>\n"
            + "Made-with: Cursor\n"
        )

        cleaned, removed_count = self.guard.sanitize_message(message)

        self.assertEqual(removed_count, 3)
        self.assertNotIn("Co-authored-by:", cleaned)
        self.assertNotIn("Signed-off-by:", cleaned)
        self.assertNotIn("Made-with: Cursor", cleaned)
        self.assertEqual(self.guard.lint_message(cleaned), [])

    def test_unknown_extra_line_still_blocks_after_sanitize(self):
        message = VALID_MESSAGE + "Unexpected-Trailer: keep visible\n"

        cleaned, removed_count = self.guard.sanitize_message(message)
        errors = self.guard.lint_message(cleaned)

        self.assertEqual(removed_count, 0)
        self.assertTrue(any("模板外的多余行" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
