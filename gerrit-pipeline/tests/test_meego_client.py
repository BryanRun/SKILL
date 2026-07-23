import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


class MeegoClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts" / "meego_client.py"
        spec = importlib.util.spec_from_file_location("meego_client_under_test", path)
        cls.meego = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(cls.meego)

    def test_extract_work_item_id_from_subject(self):
        subject = "【bug】【MEEGO-1058】修复双闪提示音"

        self.assertEqual(self.meego.extract_work_item_id(subject), "MEEGO-1058")

    def test_parse_work_item_url_extracts_context(self):
        link = self.meego.parse_work_item_url("https://project.feishu.cn/pojw7j/task1/detail/7055606222?parentUrl=%2Fpojw7j%2Ftask1%2Fhomepage%3Fwork_item_id%3D7046968769&openScene=4")

        self.assertEqual(link["base_url"], "https://project.feishu.cn")
        self.assertEqual(link["project_key"], "pojw7j")
        self.assertEqual(link["work_item_type_key"], "task1")
        self.assertEqual(link["work_item_id"], "7055606222")

    def test_parse_work_item_url_accepts_issue(self):
        link = self.meego.parse_work_item_url("https://project.feishu.cn/oc2yn3/issue/detail/7052908183?parentUrl=%2Fworkbench&openScene=2")

        self.assertEqual(link["project_key"], "oc2yn3")
        self.assertEqual(link["work_item_type_key"], "issue")
        self.assertEqual(link["work_item_id"], "7052908183")

    def test_resolve_link_without_input_url_has_no_clickable_link(self):
        original = self.meego.query_work_item
        self.meego.query_work_item = lambda *_: {}

        try:
            link = self.meego.resolve_work_item_link("【bug】【MEEGO-1058】修复双闪提示音")
        finally:
            self.meego.query_work_item = original

        self.assertEqual(link["id"], "MEEGO-1058")
        self.assertEqual(link["url"], "")
        self.assertEqual(link["source"], "id")

    def test_project_meego_config_does_not_override_builtin_resolution(self):
        cfg = {
            "meego": {"work_item_url_template": "https://root/{work_item_id}"},
            "projects": {
                "D01": {
                    "meego": {"work_item_url_template": "https://d01/{work_item_id}"},
                },
            },
        }
        original = self.meego.query_work_item
        self.meego.query_work_item = lambda *_: {}

        try:
            link = self.meego.resolve_work_item_link("【bug】【MEEGO-1058】修复双闪提示音", cfg=cfg, project_name="D01")
        finally:
            self.meego.query_work_item = original

        self.assertEqual(link["id"], "MEEGO-1058")
        self.assertEqual(link["url"], "")

    def test_resolve_link_prefers_input_url(self):
        cfg = {"meego": {"plugin_token": "dummy"}}
        original = self.meego.query_work_item
        self.meego.query_work_item = lambda *_: {}

        try:
            link = self.meego.resolve_work_item_link(
                subject="【bug】【MEEGO-1058】修复双闪提示音",
                work_item_url="https://project.feishu.cn/pojw7j/task1/detail/7055606222?openScene=4",
                cfg=cfg,
            )
        finally:
            self.meego.query_work_item = original

        self.assertEqual(link["id"], "7055606222")
        self.assertEqual(link["url"], "https://project.feishu.cn/pojw7j/task1/detail/7055606222?openScene=4")
        self.assertEqual(link["project_key"], "pojw7j")
        self.assertEqual(link["work_item_type_key"], "task1")
        self.assertEqual(link["source"], "input_url")

    def test_meego_settings_uses_builtin_credentials(self):
        settings = self.meego.meego_settings({})

        self.assertTrue(settings["plugin_id"].startswith("MII_"))
        self.assertTrue(settings["plugin_secret"])
        self.assertEqual(settings["user_key"], "7643489164528307413")
        self.assertEqual(settings["comment_path"], "/open_api/{project_key}/work_item/{work_item_type_key}/{work_item_id}/comment/create")

    def test_query_work_item_skips_api_without_user_key(self):
        original_post = self.meego._json_post
        calls = []

        def fake_post(*args, **kwargs):
            calls.append((args, kwargs))
            return {"data": []}

        self.meego._json_post = fake_post
        try:
            item = self.meego.query_work_item(
                {
                    "base_url": "https://project.feishu.cn",
                    "project_key": "demo",
                    "work_item_type_key": "story",
                    "plugin_token": "token",
                    "user_key": "",
                },
                "7055606222",
            )
        finally:
            self.meego._json_post = original_post

        self.assertEqual(item, {})
        self.assertEqual(calls, [])

    def test_query_work_item_strict_requires_user_key(self):
        with self.assertRaisesRegex(RuntimeError, "missing Meego X-USER-KEY"):
            self.meego.query_work_item(
                {
                    "base_url": "https://project.feishu.cn",
                    "project_key": "demo",
                    "work_item_type_key": "story",
                    "plugin_token": "token",
                    "user_key": "",
                },
                "7055606222",
                strict=True,
            )

    def test_build_sync_comment_contains_cr_and_sync_id(self):
        args = SimpleNamespace(
            cr="1003659",
            url="https://gerrit.example/c/1003659",
            subject="【bug】【MEEGO-1058】修复双闪提示音",
            branch="al_dev",
            score="1",
            p0="0",
            p1="0",
            p2="1",
            p3="0",
            checklist="pass",
            topic="",
            repos="",
        )

        comment = self.meego.build_sync_comment(args, {"id": "MEEGO-1058", "url": "https://meego/MEEGO-1058"})

        self.assertIn("[1003659](https://gerrit.example/c/1003659)", comment)
        self.assertIn("Sync ID: gerrit-pipeline:MEEGO-1058:1003659", comment)
        self.assertIn("Powered by gerrit-pipeline", comment)
        self.assertIn("\n---\n\nPowered by gerrit-pipeline", comment)

    def test_endpoint_template_accepts_full_url(self):
        settings = {"base_url": "https://project.feishu.cn", "project_key": "demo", "work_item_type_key": "story"}

        endpoint = self.meego.endpoint_from_template(settings, "https://api.example/items/{work_item_id}", "MEEGO-1058")

        self.assertEqual(endpoint, "https://api.example/items/MEEGO-1058")

    def test_query_work_item_uses_filter_payload(self):
        captured = {}
        original_post = self.meego._json_post

        def fake_post(url, headers=None, payload=None, timeout=30):
            captured["url"] = url
            captured["payload"] = payload
            return {"data": []}

        self.meego._json_post = fake_post
        try:
            self.meego.query_work_item(
                {
                    "base_url": "https://project.feishu.cn",
                    "project_key": "demo",
                    "work_item_type_key": "story",
                    "plugin_token": "token",
                    "user_key": "user-key",
                },
                "7055606222",
            )
        finally:
            self.meego._json_post = original_post

        self.assertEqual(captured["url"], "https://project.feishu.cn/open_api/demo/work_item/filter")
        self.assertEqual(captured["payload"]["work_item_type_keys"], ["story"])
        self.assertEqual(captured["payload"]["work_item_ids"], [7055606222])
        self.assertEqual(captured["payload"]["page_size"], 200)
        self.assertEqual(captured["payload"]["page_num"], 1)

    def test_api_headers_require_user_key_for_write_calls(self):
        with self.assertRaisesRegex(RuntimeError, "missing Meego X-USER-KEY"):
            self.meego.api_headers(
                {
                    "base_url": "https://project.feishu.cn",
                    "plugin_token": "token",
                    "user_key": "",
                },
                require_user_key=True,
            )

    def test_get_plugin_token_uses_type_zero(self):
        captured = {}
        original_post = self.meego._json_post
        self.meego._TOKEN_CACHE["token"] = None
        self.meego._TOKEN_CACHE["expire_at"] = 0

        def fake_post(url, headers=None, payload=None, timeout=30):
            captured["payload"] = payload
            return {"data": {"token": "plugin-token", "expire_time": 7200}, "error": {"code": 0}}

        self.meego._json_post = fake_post
        try:
            token = self.meego.get_plugin_token({
                "base_url": "https://project.feishu.cn",
                "plugin_token_path": "/open_api/authen/plugin_token",
                "plugin_id": "plugin-id",
                "plugin_secret": "plugin-secret",
            })
        finally:
            self.meego._json_post = original_post

        self.assertEqual(token, "plugin-token")
        self.assertEqual(captured["payload"]["type"], 0)

    def test_json_post_rejects_nested_error_code(self):
        class Response:
            status_code = 200
            text = "{}"

            def json(self):
                return {"error": {"code": 123, "msg": "denied"}}

        original_post = self.meego.requests.post
        self.meego.requests.post = lambda *_, **__: Response()
        try:
            with self.assertRaisesRegex(RuntimeError, "denied"):
                self.meego._json_post("https://project.feishu.cn/open_api/test")
        finally:
            self.meego.requests.post = original_post

    def test_post_comment_uses_create_path(self):
        captured = {}
        original_post = self.meego._json_post

        def fake_post(url, headers=None, payload=None, timeout=30):
            captured["url"] = url
            captured["payload"] = payload
            return {"data": 1}

        self.meego._json_post = fake_post
        try:
            self.meego.post_comment(
                {
                    "base_url": "https://project.feishu.cn",
                    "project_key": "demo",
                    "work_item_type_key": "story",
                    "plugin_token": "token",
                    "user_key": "user-key",
                },
                "7055606222",
                "hello",
            )
        finally:
            self.meego._json_post = original_post

        self.assertEqual(captured["url"], "https://project.feishu.cn/open_api/demo/work_item/story/7055606222/comment/create")
        self.assertEqual(captured["payload"], {"content": "hello"})

    def test_markdown_link_escapes_label(self):
        link = self.meego.format_markdown_link("MG[1058]", "https://meego/MG-1058")

        self.assertEqual(link, "[MG\\[1058\\]](https://meego/MG-1058)")

    def test_sync_fails_without_work_item_id(self):
        args = SimpleNamespace(
            subject="missing work item",
            work_item_id="",
            work_item_url="",
            project=None,
            comment_file="",
            comment_text="",
            dry=True,
            strict=False,
            cr="1003659",
            url="https://gerrit.example/c/1003659",
            branch="al_dev",
            score="1",
            p0="0",
            p1="0",
            p2="0",
            p3="0",
            checklist="pass",
            topic="",
            repos="",
            request_id="",
        )

        self.assertEqual(self.meego.cmd_sync(args), 1)


if __name__ == "__main__":
    unittest.main()
