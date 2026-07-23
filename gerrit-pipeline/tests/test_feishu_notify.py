import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


class FeishuNotifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        sys.path.insert(0, str(scripts_dir))
        path = scripts_dir / "feishu_notify.py"
        spec = importlib.util.spec_from_file_location("feishu_notify_under_test", path)
        cls.notify = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(cls.notify)

    def _args(self, **overrides):
        defaults = {
            "cr": "1003659",
            "url": "https://gerrit.example/c/1003659",
            "branch": "al_dev",
            "subject": "【bug】【MEEGO-1058】修复双闪提示音",
            "work_item_id": "",
            "work_item_url": "",
            "topic": None,
            "repos": None,
            "score": 1,
            "p0": 0,
            "p1": 0,
            "p2": 1,
            "p3": 0,
            "checklist": "pass",
            "project": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_single_card_includes_clickable_meego_link(self):
        original = self.notify.resolve_work_item_link
        self.notify.resolve_work_item_link = lambda **_: {
            "id": "MEEGO-1058",
            "url": "https://project.feishu.cn/demo/story/detail/MEEGO-1058",
        }
        try:
            card = json.loads(self.notify.build_single_card(self._args()))
        finally:
            self.notify.resolve_work_item_link = original

        rendered = json.dumps(card, ensure_ascii=False)
        self.assertIn("**Meego 工作项**", rendered)
        self.assertIn("[MEEGO-1058](https://project.feishu.cn/demo/story/detail/MEEGO-1058)", rendered)

    def test_single_card_uses_work_item_url_argument(self):
        original = self.notify.resolve_work_item_link
        self.notify.resolve_work_item_link = lambda **kwargs: {
            "id": "7055606222",
            "url": kwargs["work_item_url"],
        }
        try:
            card = json.loads(self.notify.build_single_card(self._args(
                work_item_url="https://project.feishu.cn/pojw7j/task1/detail/7055606222",
            )))
        finally:
            self.notify.resolve_work_item_link = original

        rendered = json.dumps(card, ensure_ascii=False)
        self.assertIn("[7055606222](https://project.feishu.cn/pojw7j/task1/detail/7055606222)", rendered)

    def test_topic_card_falls_back_to_plain_work_item_id(self):
        original = self.notify.resolve_work_item_link
        self.notify.resolve_work_item_link = lambda **_: {"id": "MEEGO-1058", "url": ""}
        try:
            card = json.loads(self.notify.build_topic_card(self._args(
                topic="D01_FWK_20260721",
                cr="1003659,1003660",
                url="https://gerrit.example/c/1003659,https://gerrit.example/c/1003660",
                repos="frameworks/base,packages/apps/Settings",
            )))
        finally:
            self.notify.resolve_work_item_link = original

        rendered = json.dumps(card, ensure_ascii=False)
        self.assertIn("**Meego 工作项**", rendered)
        self.assertIn("MEEGO-1058", rendered)


if __name__ == "__main__":
    unittest.main()
