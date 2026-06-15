import importlib.util
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace


class CaptureHandler(BaseHTTPRequestHandler):
    captured = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        CaptureHandler.captured = {
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "key_id": self.headers.get("X-GP-Key-Id"),
            "timestamp": self.headers.get("X-GP-Timestamp"),
            "nonce": self.headers.get("X-GP-Nonce"),
            "body_hash": self.headers.get("X-GP-Body-SHA256"),
            "signature": self.headers.get("X-GP-Signature"),
            "payload": json.loads(body.decode("utf-8")),
        }
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, fmt, *args):
        pass


class TelemetryClientTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmpdir.name
        self.old_env = {
            key: os.environ.get(key)
            for key in [
                "GERRIT_PIPELINE_TELEMETRY_URL",
                "GERRIT_PIPELINE_TELEMETRY_KEY_ID",
                "GERRIT_PIPELINE_TELEMETRY_HMAC_SECRET",
                "GERRIT_PIPELINE_TELEMETRY_TOKEN",
                "GERRIT_PIPELINE_TELEMETRY_ENABLED",
                "GERRIT_PIPELINE_TELEMETRY_INSTALL_ID",
                "GERRIT_PIPELINE_TELEMETRY_SUBMITTER",
                "GERRIT_PIPELINE_AGENT",
                "CODEX_SANDBOX",
                "CODEX_CLI",
                "CLAUDECODE",
                "CLAUDE_CODE",
            ]
        }
        for key in self.old_env:
            os.environ.pop(key, None)

        path = Path(__file__).resolve().parents[1] / "scripts" / "telemetry_client.py"
        spec = importlib.util.spec_from_file_location("telemetry_client_under_test", path)
        self.client = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(self.client)

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def _args(self, **overrides):
        defaults = {
            "event_id": "evt-test",
            "event_type": "pipeline_done",
            "mode": "submit",
            "entry_mode": "",
            "steps": "",
            "is_full_pipeline": None,
            "success": True,
            "duration_s": 0,
            "duration_ms": 123000,
            "run_id": "",
            "step_durations": "",
            "repo_count": 2,
            "agent": "codex",
            "submitter_name": "tester",
            "error_code": "",
            "failure_stage": "",
            "dry": False,
            "strict": False,
            "verbose": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_build_event_contains_expected_fields(self):
        os.environ["GERRIT_PIPELINE_TELEMETRY_INSTALL_ID"] = "install-1"
        cfg = {}

        event = self.client.build_event(self._args(), cfg)

        self.assertEqual(event["event_id"], "evt-test")
        self.assertEqual(event["schema_version"], "1.1")
        self.assertEqual(event["skill"], "gerrit-pipeline")
        self.assertEqual(event["skill_version"], "2.0.1")
        self.assertEqual(event["success"], True)
        self.assertEqual(event["duration_s"], 123.0)
        self.assertEqual(event["repo_count"], 2)
        self.assertEqual(event["agent"], "codex")
        self.assertEqual(event["agent_source"], "explicit")
        self.assertEqual(event["install_id"], "install-1")
        self.assertEqual(event["submitter_name"], "tester")

    def test_build_event_includes_pipeline_shape_fields(self):
        os.environ["GERRIT_PIPELINE_TELEMETRY_INSTALL_ID"] = "install-1"

        event = self.client.build_event(
            self._args(
                mode="unknown",
                entry_mode="submit",
                steps="submit,review,checklist,notify",
                step_durations="submit=10000,review=20000,checklist=30000,notify=40000",
            ),
            {},
        )

        self.assertEqual(event["mode"], "full_pipeline")
        self.assertEqual(event["entry_mode"], "submit")
        self.assertEqual(event["steps"], "submit,review,checklist,notify")
        self.assertTrue(event["is_full_pipeline"])
        self.assertEqual(event["submit_duration_s"], 10.0)
        self.assertEqual(event["review_duration_s"], 20.0)
        self.assertEqual(event["checklist_duration_s"], 30.0)
        self.assertEqual(event["notify_duration_s"], 40.0)
        self.assertIn('"name": "submit"', event["step_trace"])
        self.assertIn('"duration_s": 10.0', event["step_trace"])

    def test_detect_agent_falls_back_to_unknown_not_user(self):
        os.environ["USER"] = "hualei"
        original_detect = self.client.detect_agent_from_process_tree
        self.client.detect_agent_from_process_tree = lambda: ""

        try:
            agent, source = self.client.detect_agent_with_source()
        finally:
            self.client.detect_agent_from_process_tree = original_detect

        self.assertEqual(agent, "unknown")
        self.assertEqual(source, "fallback")

    def test_run_context_tracks_steps_and_duration(self):
        os.environ["GERRIT_PIPELINE_AGENT"] = "codex"
        with contextlib.redirect_stdout(io.StringIO()):
            start_rc = self.client.main([
                "--run-start",
                "--mode", "full_pipeline",
                "--entry-mode", "submit",
                "--run-id", "run-test",
            ])
            step_start_rc = self.client.main(["--run-id", "run-test", "--step-start", "submit"])
            step_finish_rc = self.client.main(["--run-id", "run-test", "--step-finish", "submit"])

        event = self.client.build_event(
            self._args(
                event_id="evt-run",
                mode="unknown",
                duration_s=0,
                duration_ms=0,
                run_id="run-test",
                agent="",
            ),
            {},
        )

        self.assertEqual(start_rc, 0)
        self.assertEqual(step_start_rc, 0)
        self.assertEqual(step_finish_rc, 0)
        self.assertEqual(event["run_id"], "run-test")
        self.assertEqual(event["mode"], "single_step")
        self.assertEqual(event["entry_mode"], "submit")
        self.assertEqual(event["steps"], "submit")
        self.assertFalse(event["is_full_pipeline"])
        self.assertEqual(event["agent"], "codex")
        self.assertIn(event["agent_source"], {"env", "run_context"})
        self.assertGreaterEqual(event["duration_s"], 0)
        self.assertIn("submit_duration_s", event)

    def test_run_context_prunes_old_and_overflow_files(self):
        original_max_contexts = self.client.MAX_RUN_CONTEXTS
        original_max_age = self.client.MAX_RUN_CONTEXT_AGE_SECONDS
        self.client.MAX_RUN_CONTEXTS = 2
        self.client.MAX_RUN_CONTEXT_AGE_SECONDS = 60
        try:
            os.makedirs(self.client.RUNS_DIR, mode=0o700, exist_ok=True)
            old_path = Path(self.client.RUNS_DIR) / "old.json"
            old_path.write_text("{}\n", encoding="utf-8")
            old_time = time.time() - 120
            os.utime(old_path, (old_time, old_time))

            for index in range(3):
                path = Path(self.client.RUNS_DIR) / f"keep-{index}.json"
                path.write_text("{}\n", encoding="utf-8")
                stamp = time.time() - (10 - index)
                os.utime(path, (stamp, stamp))

            saved = self.client.save_run_context("new", {"run_id": "new"})
            paths = list(Path(self.client.RUNS_DIR).glob("*.json"))

            self.assertTrue(saved)
            self.assertFalse(old_path.exists())
            self.assertTrue((Path(self.client.RUNS_DIR) / "new.json").exists())
            self.assertLessEqual(len(paths), 2)
        finally:
            self.client.MAX_RUN_CONTEXTS = original_max_contexts
            self.client.MAX_RUN_CONTEXT_AGE_SECONDS = original_max_age

    def test_build_event_includes_failure_stage_when_provided(self):
        os.environ["GERRIT_PIPELINE_TELEMETRY_INSTALL_ID"] = "install-1"

        event = self.client.build_event(
            self._args(success=False, error_code="step2_review_failed", failure_stage="review"),
            {},
        )

        self.assertEqual(event["error_code"], "step2_review_failed")
        self.assertEqual(event["failure_stage"], "review")

    def test_disabled_without_url_token_returns_success(self):
        os.environ["GERRIT_PIPELINE_TELEMETRY_ENABLED"] = "false"

        rc = self.client.emit(self._args())

        self.assertEqual(rc, 0)
        self.assertFalse(Path(self.client.INSTALL_ID_PATH).exists())

    def test_internal_defaults_are_used_without_user_config(self):
        cfg = self.client.load_config()
        settings = self.client.telemetry_settings(cfg)
        user_config = Path(self.tmpdir.name) / ".config" / "gerrit-pipeline" / "config.json"

        self.assertEqual(cfg, {})
        self.assertFalse(user_config.exists())
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["url"], "http://10.70.55.96:18080")
        self.assertEqual(settings["key_id"], "gerrit-pipeline-v2.0.1")
        self.assertEqual(settings["timeout"], 2.0)
        self.assertTrue(settings["hmac_secret"])

    def test_failed_send_is_queued(self):
        original_send = self.client.send_event_with_status
        self.client.send_event_with_status = lambda *args: (False, "boom", None)
        try:
            rc = self.client.emit(self._args())
        finally:
            self.client.send_event_with_status = original_send

        queued = self.client.queued_event_paths()
        self.assertEqual(rc, 0)
        self.assertEqual(len(queued), 1)
        queued_event = json.loads(Path(queued[0]).read_text(encoding="utf-8"))
        self.assertEqual(queued_event["event_id"], "evt-test")

    def test_next_emit_flushes_queued_events_before_current_event(self):
        self.client.enqueue_event({"event_id": "queued-1", "skill": "gerrit-pipeline"})
        sent = []
        original_send_events = self.client.send_events
        original_send_event = self.client.send_event_with_status

        def capture_send_events(_url, _key_id, _secret, events, _timeout):
            sent.extend(event["event_id"] for event in events)
            return True, "ok", 202

        def capture_send_event(_url, _key_id, _secret, event, _timeout):
            sent.append(event["event_id"])
            return True, "ok", 202

        self.client.send_events = capture_send_events
        self.client.send_event_with_status = capture_send_event
        try:
            rc = self.client.emit(self._args(event_id="current-1"))
        finally:
            self.client.send_events = original_send_events
            self.client.send_event_with_status = original_send_event

        self.assertEqual(rc, 0)
        self.assertEqual(sent, ["queued-1", "current-1"])
        self.assertEqual(self.client.queued_event_paths(), [])

    def test_permanent_queue_failure_moves_event_to_dead_letter(self):
        self.client.enqueue_event({"event_id": "bad-1", "skill": "gerrit-pipeline"})
        original_send_events = self.client.send_events
        self.client.send_events = lambda *args: (False, "bad request", 400)
        try:
            stats = self.client.flush_queue(
                {
                    "enabled": True,
                    "url": "http://example",
                    "key_id": "gerrit-pipeline-v2.0.1",
                    "hmac_secret": "secret",
                    "timeout": 1,
                }
            )
        finally:
            self.client.send_events = original_send_events

        dead_letter_dir = Path(self.client.DEAD_LETTER_DIR)
        dead_letters = list(dead_letter_dir.glob("*.json"))
        self.assertEqual(stats["dead_lettered"], 1)
        self.assertEqual(self.client.queued_event_paths(), [])
        self.assertEqual(len(dead_letters), 1)

    def test_background_spawn_failure_enqueues_current_event(self):
        original_popen = self.client.subprocess.Popen
        self.client.subprocess.Popen = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("nope"))
        try:
            rc = self.client.main([
                "--background",
                "--event-type", "pipeline_done",
                "--mode", "submit",
                "--success", "true",
                "--duration-ms", "1",
                "--repo-count", "1",
                "--event-id", "spawn-failed",
            ])
        finally:
            self.client.subprocess.Popen = original_popen

        queued = self.client.queued_event_paths()
        self.assertEqual(rc, 0)
        self.assertEqual(len(queued), 1)
        queued_event = json.loads(Path(queued[0]).read_text(encoding="utf-8"))
        self.assertEqual(queued_event["event_id"], "spawn-failed")

    def test_send_event_to_gateway_endpoint(self):
        server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        os.environ["GERRIT_PIPELINE_TELEMETRY_URL"] = url
        os.environ["GERRIT_PIPELINE_TELEMETRY_KEY_ID"] = "gerrit-pipeline-v2.0.1"
        os.environ["GERRIT_PIPELINE_TELEMETRY_HMAC_SECRET"] = "secret"
        os.environ["GERRIT_PIPELINE_TELEMETRY_INSTALL_ID"] = "install-2"

        rc = self.client.emit(self._args(strict=True))

        self.assertEqual(rc, 0)
        self.assertEqual(CaptureHandler.captured["path"], "/telemetry/events")
        self.assertIsNone(CaptureHandler.captured["auth"])
        self.assertEqual(CaptureHandler.captured["key_id"], "gerrit-pipeline-v2.0.1")
        self.assertTrue(CaptureHandler.captured["timestamp"])
        self.assertTrue(CaptureHandler.captured["nonce"])
        self.assertEqual(len(CaptureHandler.captured["body_hash"]), 64)
        self.assertEqual(len(CaptureHandler.captured["signature"]), 64)
        self.assertEqual(CaptureHandler.captured["payload"]["event_id"], "evt-test")

    def test_strict_mode_returns_failure_on_send_error(self):
        original_send = self.client.send_event_with_status
        self.client.send_event_with_status = lambda *args: (False, "boom", None)
        os.environ["GERRIT_PIPELINE_TELEMETRY_URL"] = "http://127.0.0.1:1"
        os.environ["GERRIT_PIPELINE_TELEMETRY_HMAC_SECRET"] = "secret"
        try:
            strict_rc = self.client.emit(self._args(strict=True))
            non_strict_rc = self.client.emit(self._args(strict=False))
        finally:
            self.client.send_event_with_status = original_send

        self.assertEqual(strict_rc, 1)
        self.assertEqual(non_strict_rc, 0)


if __name__ == "__main__":
    unittest.main()
