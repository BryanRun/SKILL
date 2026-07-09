#!/usr/bin/env python3
"""Telemetry Gateway for gerrit-pipeline usage events.

The gateway accepts internal telemetry events, stores them in a local SQLite
queue, and best-effort flushes them into a Feishu Bitable table.
"""

import datetime as _dt
import hashlib
import hmac
import json
import os
import signal
import socket
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "telemetry.sqlite3"
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
GATEWAY_VERSION = "2.0.3"

DATE_KEYS = {"received_at", "client_time"}
NUMBER_KEYS = {
    "duration_s",
    "repo_count",
    "submit_duration_s",
    "review_duration_s",
    "checklist_duration_s",
    "notify_duration_s",
}
LEGACY_NUMBER_KEYS = {
    "duration_ms",
    "submit_duration_ms",
    "review_duration_ms",
    "checklist_duration_ms",
    "notify_duration_ms",
}
BOOL_KEYS = {"success", "is_full_pipeline"}
FEISHU_FIELD_TYPE_NUMBER = 2
FEISHU_FIELD_TYPE_SINGLE_SELECT = 3
FEISHU_FIELD_TYPE_DATE = 5
LEGACY_DURATION_TO_SECONDS = {
    "duration_ms": "duration_s",
    "submit_duration_ms": "submit_duration_s",
    "review_duration_ms": "review_duration_s",
    "checklist_duration_ms": "checklist_duration_s",
    "notify_duration_ms": "notify_duration_s",
}
SECONDS_TO_LEGACY_DURATION = {
    value: key
    for key, value in LEGACY_DURATION_TO_SECONDS.items()
}

DEFAULT_FIELD_MAP = {
    "event_id": "event_id",
    "received_at": "received_at",
    "client_time": "client_time",
    "schema_version": "schema_version",
    "skill": "skill",
    "skill_version": "skill_version",
    "event_type": "event_type",
    "mode": "mode",
    "entry_mode": "entry_mode",
    "steps": "steps",
    "is_full_pipeline": "is_full_pipeline",
    "success": "success",
    "duration_s": "duration_s",
    "submit_duration_s": "submit_duration_s",
    "review_duration_s": "review_duration_s",
    "checklist_duration_s": "checklist_duration_s",
    "notify_duration_s": "notify_duration_s",
    "step_trace": "step_trace",
    "submitter_name": "submitter_name",
    "agent": "agent",
    "agent_source": "agent_source",
    "repo_count": "repo_count",
    "error_code": "error_code",
    "failure_stage": "failure_stage",
    "install_id": "install_id",
    "run_id": "run_id",
    "gateway_key_id": "gateway_key_id",
    "raw_payload": "raw_payload",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(BASE_DIR / ".env")


def getenv_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def getenv_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def utc_datetime() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def format_utc(dt: _dt.datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return format_utc(utc_datetime())


def utc_seconds_ago(seconds: int) -> str:
    return format_utc(utc_datetime() - _dt.timedelta(seconds=seconds))


def parse_date_to_ms(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return value
    text = value.strip()
    try:
        dt = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return text


def parse_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def ms_to_seconds(value: Any) -> Optional[float]:
    number = parse_number(value)
    if number is None:
        return None
    return round(max(number, 0.0) / 1000, 1)


def normalize_number(value: Any) -> Optional[Any]:
    number = parse_number(value)
    if number is None:
        return None
    if number.is_integer():
        return int(number)
    return round(number, 3)


def parse_json_env(key: str, default: Any) -> Any:
    value = os.environ.get(key)
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        print(f"WARN invalid JSON in {key}; using default", file=sys.stderr)
        return default


def parse_field_map() -> Dict[str, str]:
    overrides = parse_json_env("TELEMETRY_FIELD_MAP", {})
    if not isinstance(overrides, dict):
        print("WARN TELEMETRY_FIELD_MAP must be a JSON object; using default", file=sys.stderr)
        return dict(DEFAULT_FIELD_MAP)
    field_map = dict(DEFAULT_FIELD_MAP)
    for key, value in overrides.items():
        if key and value:
            field_map[str(key)] = str(value)
    return field_map


def parse_csv_env(key: str) -> set:
    return {
        item.strip()
        for item in os.environ.get(key, "").split(",")
        if item.strip()
    }


def parse_hmac_keys() -> Dict[str, str]:
    keys = parse_json_env("TELEMETRY_HMAC_KEYS", {})
    if not isinstance(keys, dict):
        print("WARN TELEMETRY_HMAC_KEYS must be a JSON object; using single key", file=sys.stderr)
        keys = {}
    parsed = {
        str(key): str(value)
        for key, value in keys.items()
        if key and value
    }
    key_id = os.environ.get("TELEMETRY_HMAC_KEY_ID", "gerrit-pipeline-v2.0.3")
    secret = os.environ.get("TELEMETRY_HMAC_SECRET", "")
    if key_id and secret:
        parsed.setdefault(key_id, secret)
    return parsed


class Config:
    host = os.environ.get("TELEMETRY_HOST", "0.0.0.0")
    port = getenv_int("TELEMETRY_PORT", 18080)
    admin_token = os.environ.get("TELEMETRY_ADMIN_TOKEN", "")
    hmac_keys = parse_hmac_keys()
    revoked_key_ids = parse_csv_env("TELEMETRY_REVOKED_KEY_IDS")
    signature_max_age = getenv_int("TELEMETRY_SIGNATURE_MAX_AGE_SECONDS", 300)
    nonce_ttl = max(getenv_int("TELEMETRY_NONCE_TTL_SECONDS", 600), signature_max_age)
    db_path = Path(os.environ.get("TELEMETRY_DB_PATH", str(DEFAULT_DB_PATH)))
    dry_run = getenv_bool("TELEMETRY_DRY_RUN", False)
    flush_interval = getenv_int("TELEMETRY_FLUSH_INTERVAL_SECONDS", 30)
    flush_batch_size = getenv_int("TELEMETRY_FLUSH_BATCH_SIZE", 50)
    max_attempts = getenv_int("TELEMETRY_MAX_ATTEMPTS", 20)
    in_flight_timeout = getenv_int("TELEMETRY_IN_FLIGHT_TIMEOUT_SECONDS", 300)
    request_timeout = getenv_int("TELEMETRY_HTTP_TIMEOUT_SECONDS", 10)
    max_body_bytes = getenv_int("TELEMETRY_MAX_BODY_BYTES", 64 * 1024)
    skill_allowlist = set(
        item.strip()
        for item in os.environ.get("TELEMETRY_SKILL_ALLOWLIST", "gerrit-pipeline").split(",")
        if item.strip()
    )

    feishu_app_id = os.environ.get("FEISHU_APP_ID", "")
    feishu_app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    bitable_app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
    bitable_table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID", "")
    field_map = parse_field_map()


_token_lock = threading.Lock()
_token_cache: Dict[str, Any] = {"token": "", "expire_at": 0.0}
_field_type_lock = threading.Lock()
_field_type_cache: Dict[str, Any] = {"types": {}, "expire_at": 0.0}
_nonce_lock = threading.Lock()
_stop_event = threading.Event()


def json_response(handler: BaseHTTPRequestHandler, status: int, body: Dict[str, Any]) -> None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def http_json(method: str, url: str, body: Optional[Dict[str, Any]] = None,
              headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    data = None
    request_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json; charset=utf-8")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=Config.request_timeout) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {"message": payload}
        parsed["_http_status"] = exc.code
        raise RuntimeError(json.dumps(parsed, ensure_ascii=False)) from exc


def get_tenant_token() -> str:
    if not Config.feishu_app_id or not Config.feishu_app_secret:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET not configured")
    now = time.time()
    with _token_lock:
        if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
            return _token_cache["token"]
        data = http_json(
            "POST",
            f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
            {"app_id": Config.feishu_app_id, "app_secret": Config.feishu_app_secret},
        )
        if data.get("code") != 0:
            raise RuntimeError(f"feishu token failed: {data}")
        _token_cache["token"] = data["tenant_access_token"]
        _token_cache["expire_at"] = now + int(data.get("expire", 7200))
        return _token_cache["token"]


def bitable_configured() -> bool:
    return bool(Config.feishu_app_id and Config.feishu_app_secret and
                Config.bitable_app_token and Config.bitable_table_id)


def get_bitable_field_types() -> Dict[str, int]:
    if not bitable_configured():
        return {}
    now = time.time()
    with _field_type_lock:
        if _field_type_cache["types"] and _field_type_cache["expire_at"] > now:
            return dict(_field_type_cache["types"])
        token = get_tenant_token()
        url = (
            f"{FEISHU_BASE_URL}/bitable/v1/apps/"
            f"{urllib.parse.quote(Config.bitable_app_token)}/tables/"
            f"{urllib.parse.quote(Config.bitable_table_id)}/fields?page_size=100"
        )
        data = http_json("GET", url, headers={"Authorization": f"Bearer {token}"})
        if data.get("code") != 0:
            raise RuntimeError(f"bitable list fields failed: {data}")
        types = {
            item.get("field_name"): item.get("type")
            for item in data.get("data", {}).get("items", [])
            if item.get("field_name")
        }
        _field_type_cache["types"] = types
        _field_type_cache["expire_at"] = now + 300
        return dict(types)


def normalize_bitable_value(source_key: str, value: Any, field_type: Optional[int]) -> Any:
    if value is None:
        return None
    if field_type == FEISHU_FIELD_TYPE_DATE or source_key in DATE_KEYS:
        return parse_date_to_ms(value)
    if source_key in LEGACY_DURATION_TO_SECONDS:
        return ms_to_seconds(value)
    if field_type == FEISHU_FIELD_TYPE_NUMBER or source_key in NUMBER_KEYS:
        return normalize_number(value)
    if field_type == FEISHU_FIELD_TYPE_SINGLE_SELECT:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
    if source_key in BOOL_KEYS:
        return bool(value)
    return str(value)


def event_value_for_field(source_key: str, event: Dict[str, Any]) -> Any:
    value = event.get(source_key)
    if value is None and source_key in SECONDS_TO_LEGACY_DURATION:
        legacy_value = event.get(SECONDS_TO_LEGACY_DURATION[source_key])
        if legacy_value is not None:
            return ms_to_seconds(legacy_value)
    return value


def event_to_bitable_fields(event: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    field_types = get_bitable_field_types() if not Config.dry_run else {}
    for source_key, field_name in Config.field_map.items():
        if field_types and field_name not in field_types:
            continue
        if source_key == "raw_payload":
            value = json.dumps(event, ensure_ascii=False, sort_keys=True)
        else:
            value = event_value_for_field(source_key, event)
        if value is None:
            continue
        value = normalize_bitable_value(source_key, value, field_types.get(field_name))
        if value is None:
            continue
        fields[field_name] = value
    return fields


def find_bitable_record_by_event_id(event_id: str) -> str:
    if Config.dry_run or not bitable_configured() or not event_id:
        return ""
    field_name = Config.field_map.get("event_id", "event_id")
    token = get_tenant_token()
    url = (
        f"{FEISHU_BASE_URL}/bitable/v1/apps/"
        f"{urllib.parse.quote(Config.bitable_app_token)}/tables/"
        f"{urllib.parse.quote(Config.bitable_table_id)}/records/search"
    )
    data = http_json(
        "POST",
        url,
        {
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": field_name,
                        "operator": "is",
                        "value": [str(event_id)],
                    }
                ],
            },
            "page_size": 1,
        },
        {"Authorization": f"Bearer {token}"},
    )
    if data.get("code") != 0:
        raise RuntimeError(f"bitable search record failed: {data}")
    items = data.get("data", {}).get("items", [])
    if not items:
        return ""
    return str(items[0].get("record_id") or "")


def create_bitable_record(event: Dict[str, Any]) -> str:
    if Config.dry_run:
        return "dry-run"
    if not bitable_configured():
        raise RuntimeError("Feishu Bitable is not fully configured")
    existing_record_id = find_bitable_record_by_event_id(str(event.get("event_id") or ""))
    if existing_record_id:
        return existing_record_id
    token = get_tenant_token()
    url = (
        f"{FEISHU_BASE_URL}/bitable/v1/apps/"
        f"{urllib.parse.quote(Config.bitable_app_token)}/tables/"
        f"{urllib.parse.quote(Config.bitable_table_id)}/records"
    )
    data = http_json(
        "POST",
        url,
        {"fields": event_to_bitable_fields(event)},
        {"Authorization": f"Bearer {token}"},
    )
    if data.get("code") != 0:
        raise RuntimeError(f"bitable create record failed: {data}")
    record = data.get("data", {}).get("record", {})
    return record.get("record_id", "")


def db_connect() -> sqlite3.Connection:
    Config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(Config.db_path), timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_events (
                event_id TEXT PRIMARY KEY,
                received_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                feishu_record_id TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON telemetry_events(status)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_status_updated ON telemetry_events(status, updated_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_nonces (
                key_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                seen_at TEXT NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (key_id, nonce)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_nonce_expires ON telemetry_nonces(expires_at)"
        )


def save_event(event: Dict[str, Any]) -> Tuple[bool, str]:
    accepted, duplicates = save_events([event])
    if accepted:
        return True, accepted[0]
    return False, duplicates[0] if duplicates else str(event.get("event_id") or "")


def save_events(events: Iterable[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    accepted: List[str] = []
    duplicates: List[str] = []
    now = utc_now()
    with db_connect() as conn:
        for event in events:
            event_id = str(event.get("event_id") or uuid.uuid4())
            event["event_id"] = event_id
            event.setdefault("received_at", now)
            payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
            try:
                conn.execute(
                    """
                    INSERT INTO telemetry_events
                        (event_id, received_at, payload, status, attempts, updated_at)
                    VALUES (?, ?, ?, 'pending', 0, ?)
                    """,
                    (event_id, event["received_at"], payload, now),
                )
                accepted.append(event_id)
            except sqlite3.IntegrityError:
                duplicates.append(event_id)
    return accepted, duplicates


def update_event_status(event_id: str, status: str, attempts: int,
                        error: Optional[str] = None, record_id: Optional[str] = None) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE telemetry_events
            SET status = ?, attempts = ?, last_error = ?, feishu_record_id = ?,
                updated_at = ?
            WHERE event_id = ?
            """,
            (status, attempts, error, record_id, utc_now(), event_id),
        )


def pending_events(limit: int) -> List[sqlite3.Row]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT event_id, payload, attempts
            FROM telemetry_events
            WHERE status IN ('pending', 'failed') AND attempts < ?
            ORDER BY received_at ASC
            LIMIT ?
            """,
            (Config.max_attempts, limit),
        ).fetchall()
    return list(rows)


def claim_pending_events(limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    now = utc_now()
    stale_before = utc_seconds_ago(Config.in_flight_timeout)
    with db_connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """
            SELECT event_id, payload, attempts
            FROM telemetry_events
            WHERE (
                status IN ('pending', 'failed')
                OR (status = 'sending' AND updated_at < ?)
            )
              AND attempts < ?
            ORDER BY received_at ASC
            LIMIT ?
            """,
            (stale_before, Config.max_attempts, limit),
        ).fetchall()
        if not rows:
            return []
        event_ids = [row["event_id"] for row in rows]
        placeholders = ",".join("?" for _ in event_ids)
        conn.execute(
            f"""
            UPDATE telemetry_events
            SET status = 'sending', attempts = attempts + 1, last_error = NULL,
                updated_at = ?
            WHERE event_id IN ({placeholders})
            """,
            (now, *event_ids),
        )
    return [
        {
            "event_id": row["event_id"],
            "payload": row["payload"],
            "attempts": int(row["attempts"]) + 1,
        }
        for row in rows
    ]


def event_counts() -> Dict[str, int]:
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM telemetry_events GROUP BY status"
        ).fetchall()
    return {row["status"]: int(row["c"]) for row in rows}


def flush_pending(limit: Optional[int] = None) -> Dict[str, int]:
    batch = claim_pending_events(limit or Config.flush_batch_size)
    stats = {"selected": len(batch), "sent": 0, "failed": 0}
    for event in batch:
        attempts = int(event["attempts"])
        try:
            payload = json.loads(event["payload"])
            record_id = create_bitable_record(payload)
            update_event_status(event["event_id"], "sent", attempts, None, record_id)
            stats["sent"] += 1
        except Exception as exc:  # keep the gateway alive on remote API failures
            try:
                payload = json.loads(event["payload"])
                record_id = find_bitable_record_by_event_id(str(payload.get("event_id") or ""))
            except Exception:
                record_id = ""
            if record_id:
                update_event_status(event["event_id"], "sent", attempts, None, record_id)
                stats["sent"] += 1
            else:
                update_event_status(event["event_id"], "failed", attempts, str(exc), None)
                stats["failed"] += 1
    return stats


def flush_loop() -> None:
    while not _stop_event.wait(Config.flush_interval):
        try:
            flush_pending()
        except Exception:
            traceback.print_exc()


def validate_event(event: Dict[str, Any]) -> Optional[str]:
    if not isinstance(event, dict):
        return "event must be a JSON object"
    skill = str(event.get("skill") or "")
    if Config.skill_allowlist and skill not in Config.skill_allowlist:
        return f"skill not allowed: {skill}"
    if "success" in event and not isinstance(event["success"], bool):
        return "success must be boolean"
    for key in NUMBER_KEYS | LEGACY_NUMBER_KEYS:
        if key not in event:
            continue
        if parse_number(event[key]) is None:
            return f"{key} must be number"
    if "is_full_pipeline" in event and not isinstance(event["is_full_pipeline"], bool):
        return "is_full_pipeline must be boolean"
    if "steps" in event and not isinstance(event["steps"], str):
        return "steps must be string"
    if "step_trace" in event and not isinstance(event["step_trace"], str):
        return "step_trace must be string"
    return None


def body_sha256(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body or b"").hexdigest()


def canonical_signature_payload(method: str, path: str, timestamp: str,
                                nonce: str, body_hash: str) -> str:
    return "\n".join([method.upper(), path or "/", timestamp, nonce, body_hash])


def parse_signature_timestamp(value: str) -> Optional[_dt.datetime]:
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def remember_nonce(key_id: str, nonce: str) -> bool:
    now = time.time()
    expires_at = now + Config.nonce_ttl
    with _nonce_lock:
        with db_connect() as conn:
            conn.execute("DELETE FROM telemetry_nonces WHERE expires_at < ?", (now,))
            try:
                conn.execute(
                    """
                    INSERT INTO telemetry_nonces (key_id, nonce, seen_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (key_id, nonce, utc_now(), expires_at),
                )
                return True
            except sqlite3.IntegrityError:
                return False


def check_admin_auth(handler: BaseHTTPRequestHandler) -> bool:
    if not Config.admin_token:
        return False
    auth = handler.headers.get("Authorization", "")
    expected = f"Bearer {Config.admin_token}"
    ok = hmac.compare_digest(auth, expected)
    if ok:
        setattr(handler, "telemetry_gateway_key_id", "admin")
    return ok


def require_admin_auth(handler: BaseHTTPRequestHandler) -> bool:
    if not Config.admin_token:
        json_response(handler, 503, {"ok": False, "error": "admin_auth_not_configured"})
        return False
    if not check_admin_auth(handler):
        json_response(handler, 401, {"ok": False, "error": "unauthorized"})
        return False
    return True


def check_hmac_auth(handler: BaseHTTPRequestHandler, raw_body: bytes) -> bool:
    if not Config.hmac_keys:
        json_response(handler, 503, {"ok": False, "error": "gateway_auth_not_configured"})
        return False

    key_id = handler.headers.get("X-GP-Key-Id", "")
    timestamp = handler.headers.get("X-GP-Timestamp", "")
    nonce = handler.headers.get("X-GP-Nonce", "")
    supplied_body_hash = handler.headers.get("X-GP-Body-SHA256", "")
    supplied_signature = handler.headers.get("X-GP-Signature", "")
    if not all([key_id, timestamp, nonce, supplied_body_hash, supplied_signature]):
        json_response(handler, 401, {"ok": False, "error": "missing_signature_headers"})
        return False
    if key_id in Config.revoked_key_ids:
        json_response(handler, 403, {"ok": False, "error": "key_revoked"})
        return False
    secret = Config.hmac_keys.get(key_id)
    if not secret:
        json_response(handler, 401, {"ok": False, "error": "unknown_key_id"})
        return False
    if len(nonce) > 128 or len(nonce) < 8:
        json_response(handler, 401, {"ok": False, "error": "invalid_nonce"})
        return False

    parsed_ts = parse_signature_timestamp(timestamp)
    if parsed_ts is None:
        json_response(handler, 401, {"ok": False, "error": "invalid_signature_timestamp"})
        return False
    age = abs((utc_datetime() - parsed_ts).total_seconds())
    if age > max(Config.signature_max_age, 1):
        json_response(handler, 401, {"ok": False, "error": "signature_timestamp_out_of_window"})
        return False

    actual_body_hash = body_sha256(raw_body)
    if not hmac.compare_digest(actual_body_hash, supplied_body_hash):
        json_response(handler, 401, {"ok": False, "error": "body_hash_mismatch"})
        return False

    path = urllib.parse.urlparse(handler.path).path or "/"
    canonical = canonical_signature_payload(
        handler.command,
        path,
        timestamp,
        nonce,
        actual_body_hash,
    )
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, supplied_signature):
        json_response(handler, 401, {"ok": False, "error": "invalid_signature"})
        return False

    try:
        nonce_is_new = remember_nonce(key_id, nonce)
    except Exception as exc:
        json_response(handler, 503, {
            "ok": False,
            "error": "nonce_store_unavailable",
            "detail": str(exc),
        })
        return False
    if not nonce_is_new:
        json_response(handler, 401, {"ok": False, "error": "replay_detected"})
        return False
    setattr(handler, "telemetry_gateway_key_id", key_id)
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = f"TelemetryGateway/{GATEWAY_VERSION}"

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            json_response(self, 200, {"ok": True, "service": "telemetry-gateway"})
            return
        if path == "/version":
            if not require_admin_auth(self):
                return
            json_response(self, 200, {
                "ok": True,
                "service": "telemetry-gateway",
                "version": GATEWAY_VERSION,
                "server_version": self.server_version,
            })
            return
        if path == "/readyz":
            if not require_admin_auth(self):
                return
            body: Dict[str, Any] = {
                "ok": True,
                "bitable_configured": bitable_configured(),
                "dry_run": Config.dry_run,
                "db_path": str(Config.db_path),
                "field_count": 0,
            }
            status = 200
            if bitable_configured() and not Config.dry_run:
                try:
                    body["field_count"] = len(get_bitable_field_types())
                except Exception as exc:
                    body.update({"ok": False, "error": "bitable_unreachable", "detail": str(exc)})
                    status = 503
            json_response(self, status, body)
            return
        if path == "/metrics":
            if not require_admin_auth(self):
                return
            json_response(self, 200, {"ok": True, "counts": event_counts()})
            return
        json_response(self, 404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/telemetry/flush":
            if not require_admin_auth(self):
                return
            stats = flush_pending()
            json_response(self, 200, {"ok": True, "flush": stats, "counts": event_counts()})
            return
        if path not in {"/telemetry", "/telemetry/events"}:
            json_response(self, 404, {"ok": False, "error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            json_response(self, 400, {"ok": False, "error": "invalid_content_length"})
            return
        if content_length <= 0:
            json_response(self, 400, {"ok": False, "error": "invalid_body_size"})
            return
        if content_length > Config.max_body_bytes:
            json_response(self, 413, {"ok": False, "error": "invalid_body_size"})
            return
        raw = self.rfile.read(content_length)
        if not check_hmac_auth(self, raw):
            return
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            json_response(self, 400, {"ok": False, "error": "invalid_json"})
            return

        events = data.get("events") if isinstance(data, dict) and "events" in data else data
        if isinstance(events, dict):
            event_list = [events]
        elif isinstance(events, list):
            event_list = events
        else:
            json_response(self, 400, {"ok": False, "error": "event_or_events_required"})
            return

        for index, event in enumerate(event_list):
            error = validate_event(event)
            if error:
                json_response(self, 400, {"ok": False, "error": error, "index": index})
                return

        gateway_key_id = getattr(self, "telemetry_gateway_key_id", "")
        if gateway_key_id:
            for event in event_list:
                event["gateway_key_id"] = gateway_key_id

        accepted, duplicates = save_events(event_list)
        json_response(self, 202, {
            "ok": True,
            "accepted": len(accepted),
            "duplicates": len(duplicates),
            "event_ids": accepted,
            "queued": len(accepted),
            "counts": event_counts(),
        })

    def log_message(self, fmt: str, *args: Any) -> None:
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts} {self.client_address[0]} {fmt % args}", flush=True)


def main() -> int:
    init_db()
    worker = threading.Thread(target=flush_loop, name="telemetry-flusher", daemon=True)
    worker.start()

    httpd = ThreadingHTTPServer((Config.host, Config.port), Handler)

    def handle_signal(_signum: int, _frame: Any) -> None:
        _stop_event.set()
        threading.Thread(target=httpd.shutdown, name="telemetry-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print(
        f"telemetry-gateway listening on {Config.host}:{Config.port}; "
        f"db={Config.db_path}; dry_run={Config.dry_run}; "
        f"host={socket.gethostname()}",
        flush=True,
    )
    httpd.serve_forever()
    httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
