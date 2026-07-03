import hashlib
import hmac
import importlib.util
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


os.environ.update(
    {
        "TELEMETRY_ADMIN_TOKEN": "admin-token",
        "TELEMETRY_HMAC_KEYS": '{"gerrit-pipeline-v2.0.2":"old-test-secret","gerrit-pipeline-v2.0.3":"test-secret"}',
        "TELEMETRY_REVOKED_KEY_IDS": "",
        "TELEMETRY_DRY_RUN": "true",
        "TELEMETRY_FIELD_MAP": "",
        "FEISHU_APP_ID": "",
        "FEISHU_APP_SECRET": "",
        "FEISHU_BITABLE_APP_TOKEN": "",
        "FEISHU_BITABLE_TABLE_ID": "",
    }
)

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
spec = importlib.util.spec_from_file_location("telemetry_gateway_app", APP_PATH)
app = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(app)


class QuietHandler(app.Handler):
    def log_message(self, fmt, *args):
        pass


class TelemetryGatewayTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_config = {
            "db_path": app.Config.db_path,
            "dry_run": app.Config.dry_run,
            "admin_token": app.Config.admin_token,
            "hmac_keys": app.Config.hmac_keys,
            "revoked_key_ids": app.Config.revoked_key_ids,
            "signature_max_age": app.Config.signature_max_age,
            "nonce_ttl": app.Config.nonce_ttl,
            "max_attempts": app.Config.max_attempts,
            "in_flight_timeout": app.Config.in_flight_timeout,
            "flush_batch_size": app.Config.flush_batch_size,
            "max_body_bytes": app.Config.max_body_bytes,
            "skill_allowlist": app.Config.skill_allowlist,
            "feishu_app_id": app.Config.feishu_app_id,
            "feishu_app_secret": app.Config.feishu_app_secret,
            "bitable_app_token": app.Config.bitable_app_token,
            "bitable_table_id": app.Config.bitable_table_id,
            "field_map": app.Config.field_map,
        }
        app.Config.db_path = Path(self.tmpdir.name) / "telemetry.sqlite3"
        app.Config.dry_run = True
        app.Config.admin_token = "admin-token"
        app.Config.hmac_keys = {
            "gerrit-pipeline-v2.0.2": "old-test-secret",
            "gerrit-pipeline-v2.0.3": "test-secret",
        }
        app.Config.revoked_key_ids = set()
        app.Config.signature_max_age = 300
        app.Config.nonce_ttl = 600
        app.Config.max_attempts = 3
        app.Config.in_flight_timeout = 300
        app.Config.flush_batch_size = 50
        app.Config.max_body_bytes = 1024
        app.Config.skill_allowlist = {"gerrit-pipeline"}
        app.Config.feishu_app_id = ""
        app.Config.feishu_app_secret = ""
        app.Config.bitable_app_token = ""
        app.Config.bitable_table_id = ""
        app.Config.field_map = dict(app.DEFAULT_FIELD_MAP)
        app.init_db()

    def tearDown(self):
        for key, value in self.original_config.items():
            setattr(app.Config, key, value)
        self.tmpdir.cleanup()

    def _start_server(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        return server

    def _json_request(self, server, method, path, payload=None, headers=None):
        url = f"http://127.0.0.1:{server.server_address[1]}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = dict(headers or {})
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8")
                return resp.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, json.loads(body)

    def _signed_headers(
        self,
        method,
        path,
        payload=None,
        nonce="nonce-test",
        key_id="gerrit-pipeline-v2.0.3",
        secret="test-secret",
    ):
        raw = b"" if payload is None else json.dumps(payload).encode("utf-8")
        body_hash = hashlib.sha256(raw).hexdigest()
        timestamp = app.utc_now()
        canonical = app.canonical_signature_payload(
            method,
            path.split("?", 1)[0],
            timestamp,
            nonce,
            body_hash,
        )
        signature = hmac.new(
            secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-GP-Key-Id": key_id,
            "X-GP-Timestamp": timestamp,
            "X-GP-Nonce": nonce,
            "X-GP-Body-SHA256": body_hash,
            "X-GP-Signature": signature,
        }

    def test_duplicate_event_is_not_inserted_twice(self):
        event = {
            "event_id": "evt-1",
            "skill": "gerrit-pipeline",
            "success": True,
            "duration_s": 12.0,
        }
        inserted, event_id = app.save_event(dict(event))
        duplicate_inserted, duplicate_id = app.save_event(dict(event))

        self.assertTrue(inserted)
        self.assertFalse(duplicate_inserted)
        self.assertEqual(event_id, duplicate_id)
        self.assertEqual(app.event_counts(), {"pending": 1})

        self.assertEqual(app.flush_pending(), {"selected": 1, "sent": 1, "failed": 0})
        self.assertEqual(app.event_counts(), {"sent": 1})

    def test_claim_marks_events_sending_and_skips_active_claims(self):
        app.save_event({"event_id": "evt-claim", "skill": "gerrit-pipeline"})

        first_claim = app.claim_pending_events(10)
        second_claim = app.claim_pending_events(10)

        self.assertEqual([item["event_id"] for item in first_claim], ["evt-claim"])
        self.assertEqual(first_claim[0]["attempts"], 1)
        self.assertEqual(second_claim, [])
        self.assertEqual(app.event_counts(), {"sending": 1})

    def test_claim_retries_stale_sending_events(self):
        app.Config.in_flight_timeout = 1
        app.save_event({"event_id": "evt-stale", "skill": "gerrit-pipeline"})
        app.claim_pending_events(10)
        stale_time = app.format_utc(app.utc_datetime() - app._dt.timedelta(seconds=2))
        with app.db_connect() as conn:
            conn.execute(
                "UPDATE telemetry_events SET updated_at = ? WHERE event_id = ?",
                (stale_time, "evt-stale"),
            )

        retry_claim = app.claim_pending_events(10)

        self.assertEqual([item["event_id"] for item in retry_claim], ["evt-stale"])
        self.assertEqual(retry_claim[0]["attempts"], 2)

    def test_field_map_merges_over_defaults(self):
        old_value = os.environ.get("TELEMETRY_FIELD_MAP")
        os.environ["TELEMETRY_FIELD_MAP"] = '{"submitter_name": "Submitter"}'
        try:
            field_map = app.parse_field_map()
        finally:
            if old_value is None:
                os.environ.pop("TELEMETRY_FIELD_MAP", None)
            else:
                os.environ["TELEMETRY_FIELD_MAP"] = old_value

        self.assertEqual(field_map["skill"], "skill")
        self.assertEqual(field_map["submitter_name"], "Submitter")

    def test_event_to_bitable_fields_skips_missing_bitable_columns(self):
        app.Config.dry_run = False
        original_get_fields = app.get_bitable_field_types
        app.get_bitable_field_types = lambda: {"event_id": 1, "skill": 1}
        try:
            fields = app.event_to_bitable_fields({
                "event_id": "evt-columns",
                "skill": "gerrit-pipeline",
                "failure_stage": "review",
                "gateway_key_id": "gerrit-pipeline-v2.0.3",
            })
        finally:
            app.get_bitable_field_types = original_get_fields

        self.assertEqual(fields, {"event_id": "evt-columns", "skill": "gerrit-pipeline"})

    def test_event_to_bitable_fields_includes_pipeline_shape_fields(self):
        fields = app.event_to_bitable_fields({
            "event_id": "evt-shape",
            "skill": "gerrit-pipeline",
            "mode": "full_pipeline",
            "entry_mode": "submit",
            "steps": "submit,review,checklist,notify",
            "is_full_pipeline": True,
            "agent": "codex",
            "agent_source": "explicit",
            "duration_s": 100.0,
            "submit_duration_s": 10.0,
            "review_duration_s": 20.0,
            "checklist_duration_s": 30.0,
            "notify_duration_s": 40.0,
            "step_trace": '[{"name":"submit","duration_s":10.0}]',
            "run_id": "run-1",
        })

        self.assertEqual(fields["entry_mode"], "submit")
        self.assertEqual(fields["steps"], "submit,review,checklist,notify")
        self.assertTrue(fields["is_full_pipeline"])
        self.assertEqual(fields["agent_source"], "explicit")
        self.assertEqual(fields["duration_s"], 100)
        self.assertEqual(fields["submit_duration_s"], 10)
        self.assertEqual(fields["review_duration_s"], 20)
        self.assertEqual(fields["checklist_duration_s"], 30)
        self.assertEqual(fields["notify_duration_s"], 40)
        self.assertEqual(fields["run_id"], "run-1")

    def test_event_to_bitable_fields_derives_seconds_from_legacy_ms(self):
        fields = app.event_to_bitable_fields({
            "event_id": "evt-legacy-duration",
            "skill": "gerrit-pipeline",
            "duration_ms": 123000,
            "submit_duration_ms": 10000,
        })

        self.assertEqual(fields["duration_s"], 123)
        self.assertEqual(fields["submit_duration_s"], 10)

    def test_validate_event_rejects_invalid_new_field_types(self):
        self.assertEqual(
            app.validate_event({
                "event_id": "evt-bad-duration",
                "skill": "gerrit-pipeline",
                "success": True,
                "submit_duration_s": "bad",
            }),
            "submit_duration_s must be number",
        )
        self.assertEqual(
            app.validate_event({
                "event_id": "evt-bad-full",
                "skill": "gerrit-pipeline",
                "success": True,
                "is_full_pipeline": "true",
            }),
            "is_full_pipeline must be boolean",
        )

    def test_http_event_submission_queues_without_sync_flush(self):
        server = self._start_server()
        payload = {
            "event_id": "evt-http",
            "skill": "gerrit-pipeline",
            "success": True,
            "duration_s": 123.0,
        }

        status, body = self._json_request(
            server,
            "POST",
            "/telemetry/events?source=test",
            payload,
            self._signed_headers("POST", "/telemetry/events?source=test", payload),
        )
        with app.db_connect() as conn:
            row = conn.execute(
                "SELECT payload FROM telemetry_events WHERE event_id = ?",
                ("evt-http",),
            ).fetchone()
        saved_payload = json.loads(row["payload"])
        metric_status, metric_body = self._json_request(
            server,
            "GET",
            "/metrics",
            headers={"Authorization": "Bearer admin-token"},
        )
        flush_status, flush_body = self._json_request(
            server,
            "POST",
            "/telemetry/flush",
            headers={"Authorization": "Bearer admin-token"},
        )

        self.assertEqual(status, 202)
        self.assertEqual(body["accepted"], 1)
        self.assertEqual(body["queued"], 1)
        self.assertEqual(saved_payload["gateway_key_id"], "gerrit-pipeline-v2.0.3")
        self.assertEqual(metric_status, 200)
        self.assertEqual(metric_body["counts"], {"pending": 1})
        self.assertEqual(flush_status, 200)
        self.assertEqual(flush_body["flush"], {"selected": 1, "sent": 1, "failed": 0})
        self.assertEqual(flush_body["counts"], {"sent": 1})

    def test_legacy_hmac_key_is_accepted_during_rotation(self):
        server = self._start_server()
        payload = {
            "event_id": "evt-legacy-key",
            "skill": "gerrit-pipeline",
            "skill_version": "2.0.2",
            "success": True,
            "duration_s": 123.0,
        }

        status, body = self._json_request(
            server,
            "POST",
            "/telemetry/events",
            payload,
            self._signed_headers(
                "POST",
                "/telemetry/events",
                payload,
                nonce="nonce-legacy-key",
                key_id="gerrit-pipeline-v2.0.2",
                secret="old-test-secret",
            ),
        )
        with app.db_connect() as conn:
            row = conn.execute(
                "SELECT payload FROM telemetry_events WHERE event_id = ?",
                ("evt-legacy-key",),
            ).fetchone()
        saved_payload = json.loads(row["payload"])

        self.assertEqual(status, 202)
        self.assertEqual(body["accepted"], 1)
        self.assertEqual(saved_payload["gateway_key_id"], "gerrit-pipeline-v2.0.2")

    def test_hmac_nonce_replay_is_rejected(self):
        server = self._start_server()
        payload = {
            "event_id": "evt-replay",
            "skill": "gerrit-pipeline",
            "success": True,
            "duration_s": 123.0,
        }
        headers = self._signed_headers("POST", "/telemetry/events", payload, nonce="nonce-replay")

        first_status, first_body = self._json_request(
            server,
            "POST",
            "/telemetry/events",
            payload,
            headers,
        )
        second_status, second_body = self._json_request(
            server,
            "POST",
            "/telemetry/events",
            payload,
            headers,
        )

        self.assertEqual(first_status, 202)
        self.assertEqual(first_body["accepted"], 1)
        self.assertEqual(second_status, 401)
        self.assertEqual(second_body["error"], "replay_detected")

    def test_revoked_hmac_key_is_rejected(self):
        server = self._start_server()
        app.Config.revoked_key_ids = {"gerrit-pipeline-v2.0.3"}
        payload = {
            "event_id": "evt-revoked",
            "skill": "gerrit-pipeline",
            "success": True,
            "duration_s": 123.0,
        }

        status, body = self._json_request(
            server,
            "POST",
            "/telemetry/events",
            payload,
            self._signed_headers("POST", "/telemetry/events", payload, nonce="nonce-revoked"),
        )

        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "key_revoked")

    def test_event_submission_rejects_admin_token_without_hmac(self):
        server = self._start_server()
        payload = {
            "event_id": "evt-admin-write",
            "skill": "gerrit-pipeline",
            "success": True,
            "duration_s": 123.0,
        }

        status, body = self._json_request(
            server,
            "POST",
            "/telemetry/events",
            payload,
            {"Authorization": "Bearer admin-token"},
        )

        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "missing_signature_headers")
        self.assertEqual(app.event_counts(), {})

    def test_invalid_batch_does_not_partially_insert(self):
        server = self._start_server()
        payload = {
            "events": [
                {
                    "event_id": "evt-good",
                    "skill": "gerrit-pipeline",
                    "success": True,
                    "duration_s": 123.0,
                },
                {
                    "event_id": "evt-bad",
                    "skill": "gerrit-pipeline",
                    "success": "true",
                },
            ]
        }

        status, body = self._json_request(
            server,
            "POST",
            "/telemetry/events",
            payload,
            self._signed_headers("POST", "/telemetry/events", payload, nonce="nonce-batch"),
        )

        self.assertEqual(status, 400)
        self.assertEqual(body["index"], 1)
        self.assertEqual(app.event_counts(), {})

    def test_create_bitable_record_reuses_existing_event_id(self):
        app.Config.dry_run = False
        app.Config.feishu_app_id = "cli_xxx"
        app.Config.feishu_app_secret = "secret"
        app.Config.bitable_app_token = "app"
        app.Config.bitable_table_id = "table"
        original_get_tenant_token = app.get_tenant_token
        original_http_json = app.http_json
        calls = []

        def fake_http_json(method, url, body=None, headers=None):
            calls.append((method, url, body))
            if url.endswith("/records/search"):
                return {"code": 0, "data": {"items": [{"record_id": "rec-existing"}]}}
            if url.endswith("/records"):
                raise AssertionError("create should not be called when event_id already exists")
            return {"code": 0}

        app.get_tenant_token = lambda: "tenant-token"
        app.http_json = fake_http_json
        try:
            record_id = app.create_bitable_record({
                "event_id": "evt-existing",
                "skill": "gerrit-pipeline",
                "success": True,
            })
        finally:
            app.get_tenant_token = original_get_tenant_token
            app.http_json = original_http_json

        self.assertEqual(record_id, "rec-existing")
        self.assertEqual(len(calls), 1)

    def test_invalid_content_length_returns_json_error(self):
        server = self._start_server()
        host, port = server.server_address

        with socket.create_connection((host, port), timeout=5) as sock:
            sock.sendall(
                b"POST /telemetry/events HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Authorization: Bearer admin-token\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: nope\r\n"
                b"Connection: close\r\n"
                b"\r\n"
            )
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk

        self.assertIn(b"400", response.splitlines()[0])
        self.assertIn(b"invalid_content_length", response)

    def test_readyz_requires_admin_token(self):
        server = self._start_server()

        status, body = self._json_request(server, "GET", "/readyz")

        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "unauthorized")

    def test_readyz_reports_bitable_failure_as_json(self):
        server = self._start_server()
        app.Config.dry_run = False
        app.Config.feishu_app_id = "cli_xxx"
        app.Config.feishu_app_secret = "secret"
        app.Config.bitable_app_token = "app"
        app.Config.bitable_table_id = "table"
        original_get_fields = app.get_bitable_field_types

        def fail_get_fields():
            raise RuntimeError("field lookup failed")

        app.get_bitable_field_types = fail_get_fields
        try:
            status, body = self._json_request(
                server,
                "GET",
                "/readyz",
                headers={"Authorization": "Bearer admin-token"},
            )
        finally:
            app.get_bitable_field_types = original_get_fields

        self.assertEqual(status, 503)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "bitable_unreachable")


if __name__ == "__main__":
    unittest.main()
