#!/usr/bin/env python3
"""Best-effort telemetry client for gerrit-pipeline runs."""

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_DIR = os.path.expanduser("~/.config/gerrit-pipeline")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_DIR = os.path.expanduser("~/.cache/gerrit-pipeline")
QUEUE_DIR = os.path.join(CACHE_DIR, "telemetry-queue")
DEAD_LETTER_DIR = os.path.join(CACHE_DIR, "telemetry-dead-letter")
DEFAULTS_PATH = os.path.join(SCRIPT_DIR, "telemetry_defaults.json")
INSTALL_ID_PATH = os.path.join(CONFIG_DIR, "install_id")
BACKGROUND_ENV = "GERRIT_PIPELINE_TELEMETRY_BACKGROUND"
SKILL_NAME = "gerrit-pipeline"
SCHEMA_VERSION = "1.0"
MAX_QUEUE_EVENTS = 200
MAX_DEAD_LETTER_EVENTS = 100
FLUSH_BATCH_SIZE = 50
MAX_QUEUE_AGE_SECONDS = 14 * 24 * 60 * 60
PERMANENT_HTTP_STATUS = {400, 401, 403, 413}

DEFAULT_TELEMETRY = {
    "enabled": True,
    "url": "http://10.70.55.96:18080",
    "key_id": "gerrit-pipeline-v2.0.0",
    "timeout_seconds": 2,
}


def parse_bool(value):
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean: {value}")


def env_bool(key):
    value = os.environ.get(key)
    if value is None or value == "":
        return None
    try:
        return parse_bool(value)
    except argparse.ArgumentTypeError:
        return None


def optional_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        return parse_bool(value)
    except argparse.ArgumentTypeError:
        return None


def read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_internal_defaults():
    defaults = dict(DEFAULT_TELEMETRY)
    packaged = read_json_file(DEFAULTS_PATH)
    if isinstance(packaged, dict):
        for key in (
            "enabled",
            "url",
            "key_id",
            "hmac_secret",
            "token",
            "timeout_seconds",
            "install_id",
        ):
            if packaged.get(key) not in (None, ""):
                defaults[key] = packaged[key]
    return defaults


def load_config():
    data = read_json_file(CONFIG_PATH)
    return data if isinstance(data, dict) else {}


def read_version():
    readme = os.path.join(os.path.dirname(__file__), "..", "README.md")
    try:
        with open(readme, encoding="utf-8") as f:
            for line in f:
                match = re.match(r"\*\*版本：v([\d.]+)\*\*", line.strip())
                if match:
                    return match.group(1)
    except OSError:
        pass
    return "unknown"


def telemetry_settings(cfg):
    defaults = load_internal_defaults()
    url = (
        os.environ.get("GERRIT_PIPELINE_TELEMETRY_URL")
        or defaults["url"]
    )
    key_id = (
        os.environ.get("GERRIT_PIPELINE_TELEMETRY_KEY_ID")
        or defaults.get("key_id")
        or f"{SKILL_NAME}-v{read_version()}"
    )
    hmac_secret = (
        os.environ.get("GERRIT_PIPELINE_TELEMETRY_HMAC_SECRET")
        or os.environ.get("GERRIT_PIPELINE_TELEMETRY_TOKEN")
        or defaults.get("hmac_secret")
        or defaults.get("token")
        or ""
    )
    timeout_raw = (
        os.environ.get("GERRIT_PIPELINE_TELEMETRY_TIMEOUT_SECONDS")
        or defaults["timeout_seconds"]
    )
    try:
        timeout = max(float(timeout_raw), 0.1)
    except (TypeError, ValueError):
        timeout = 2.0

    enabled = env_bool("GERRIT_PIPELINE_TELEMETRY_ENABLED")
    if enabled is None:
        enabled = bool(defaults["enabled"])
    else:
        enabled = bool(enabled)

    return {
        "enabled": enabled,
        "url": str(url),
        "key_id": str(key_id),
        "hmac_secret": str(hmac_secret),
        "timeout": timeout,
    }


def get_submitter_name(cfg):
    explicit = os.environ.get("GERRIT_PIPELINE_TELEMETRY_SUBMITTER")
    if explicit:
        return explicit
    feishu = cfg.get("feishu", {}) if isinstance(cfg.get("feishu", {}), dict) else {}
    submitter = feishu.get("submitter", {}) if isinstance(feishu.get("submitter", {}), dict) else {}
    return submitter.get("name") or ""


def detect_agent():
    explicit = os.environ.get("GERRIT_PIPELINE_AGENT")
    if explicit:
        return explicit
    if os.environ.get("CODEX_SANDBOX") or os.environ.get("CODEX_CLI"):
        return "codex"
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE"):
        return "claude-code"
    return os.environ.get("USER", "unknown")


def get_install_id(cfg):
    explicit = os.environ.get("GERRIT_PIPELINE_TELEMETRY_INSTALL_ID")
    if explicit:
        return explicit
    defaults = load_internal_defaults()
    if defaults.get("install_id"):
        return str(defaults["install_id"])

    try:
        with open(INSTALL_ID_PATH, "r", encoding="utf-8") as f:
            value = f.read().strip()
            if value:
                return value
    except OSError:
        pass

    value = str(uuid.uuid4())
    try:
        os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
        fd = os.open(INSTALL_ID_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value + "\n")
    except FileExistsError:
        try:
            with open(INSTALL_ID_PATH, "r", encoding="utf-8") as f:
                return f.read().strip() or value
        except OSError:
            return value
    except OSError:
        return value
    return value


def client_time():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def build_event(args, cfg):
    event = {
        "event_id": args.event_id or str(uuid.uuid4()),
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "skill_version": read_version(),
        "event_type": args.event_type,
        "mode": args.mode,
        "success": bool(args.success),
        "duration_ms": max(int(args.duration_ms), 0),
        "repo_count": max(int(args.repo_count), 0),
        "client_time": client_time(),
        "agent": args.agent or detect_agent(),
        "install_id": get_install_id(cfg),
    }
    submitter_name = args.submitter_name or get_submitter_name(cfg)
    if submitter_name:
        event["submitter_name"] = submitter_name
    if args.error_code:
        event["error_code"] = args.error_code
    if getattr(args, "failure_stage", ""):
        event["failure_stage"] = args.failure_stage
    return event


def endpoint_url(base_url):
    url = base_url.rstrip("/")
    if url.endswith("/telemetry") or url.endswith("/telemetry/events"):
        return url
    return f"{url}/telemetry/events"


def body_sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def signature_timestamp():
    return client_time()


def canonical_signature_payload(method, path, timestamp, nonce, body_hash):
    return "\n".join([method.upper(), path or "/", timestamp, nonce, body_hash])


def build_signature_headers(method, url, payload, key_id, hmac_secret):
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    timestamp = signature_timestamp()
    nonce = str(uuid.uuid4())
    digest = body_sha256(payload)
    canonical = canonical_signature_payload(method, path, timestamp, nonce, digest)
    signature = hmac.new(
        hmac_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-GP-Key-Id": key_id,
        "X-GP-Timestamp": timestamp,
        "X-GP-Nonce": nonce,
        "X-GP-Body-SHA256": digest,
        "X-GP-Signature": signature,
    }


def send_payload(url, key_id, hmac_secret, payload_obj, timeout):
    payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
    final_url = endpoint_url(url)
    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }
    headers.update(build_signature_headers("POST", final_url, payload, key_id, hmac_secret))
    req = urllib.request.Request(
        final_url,
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return 200 <= resp.status < 300, body, resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {body}", exc.code
    except Exception as exc:
        return False, str(exc), None


def send_event_with_status(url, key_id, hmac_secret, event, timeout):
    return send_payload(url, key_id, hmac_secret, event, timeout)


def send_event(url, key_id, hmac_secret, event, timeout):
    ok, detail, _status = send_event_with_status(url, key_id, hmac_secret, event, timeout)
    return ok, detail


def send_events(url, key_id, hmac_secret, events, timeout):
    return send_payload(url, key_id, hmac_secret, {"events": events}, timeout)


def is_permanent_failure(status):
    return status in PERMANENT_HTTP_STATUS


def is_configured(settings):
    return bool(
        settings["enabled"]
        and settings["url"]
        and settings["key_id"]
        and settings["hmac_secret"]
    )


def queue_path_for_event(event):
    event_id = str(event.get("event_id") or uuid.uuid4())
    safe_event_id = re.sub(r"[^A-Za-z0-9_.-]", "_", event_id)[:120]
    return os.path.join(QUEUE_DIR, f"{int(time.time() * 1000)}-{safe_event_id}.json")


def enqueue_event(event):
    try:
        os.makedirs(QUEUE_DIR, mode=0o700, exist_ok=True)
        path = queue_path_for_event(event)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(event, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        prune_queue()
        return True
    except OSError:
        return False


def dead_letter_path_for_event(event):
    event_id = str(event.get("event_id") or uuid.uuid4())
    safe_event_id = re.sub(r"[^A-Za-z0-9_.-]", "_", event_id)[:120]
    return os.path.join(DEAD_LETTER_DIR, f"{int(time.time() * 1000)}-{safe_event_id}.json")


def prune_dead_letters():
    try:
        paths = [
            os.path.join(DEAD_LETTER_DIR, name)
            for name in os.listdir(DEAD_LETTER_DIR)
            if name.endswith(".json")
        ]
    except OSError:
        return
    paths = sorted(paths, key=lambda path: (os.path.getmtime(path), path))
    overflow = len(paths) - MAX_DEAD_LETTER_EVENTS
    for path in paths[:max(0, overflow)]:
        try:
            os.unlink(path)
        except OSError:
            pass


def dead_letter_event(event, detail):
    try:
        os.makedirs(DEAD_LETTER_DIR, mode=0o700, exist_ok=True)
        path = dead_letter_path_for_event(event)
        payload = {
            "dead_lettered_at": client_time(),
            "error": detail,
            "event": event,
        }
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        prune_dead_letters()
        return True
    except OSError:
        return False


def queued_event_paths():
    try:
        entries = [
            os.path.join(QUEUE_DIR, name)
            for name in os.listdir(QUEUE_DIR)
            if name.endswith(".json")
        ]
    except OSError:
        return []
    return sorted(entries, key=lambda path: (os.path.getmtime(path), path))


def prune_queue():
    paths = queued_event_paths()
    if not paths:
        return
    now = time.time()
    for path in paths:
        try:
            if now - os.path.getmtime(path) > MAX_QUEUE_AGE_SECONDS:
                os.unlink(path)
        except OSError:
            pass
    paths = queued_event_paths()
    overflow = len(paths) - MAX_QUEUE_EVENTS
    for path in paths[:max(0, overflow)]:
        try:
            os.unlink(path)
        except OSError:
            pass


def flush_queue(settings, verbose=False):
    if not is_configured(settings):
        return {"selected": 0, "sent": 0, "failed": 0, "dead_lettered": 0}
    prune_queue()
    stats = {"selected": 0, "sent": 0, "failed": 0, "dead_lettered": 0}
    paths = queued_event_paths()
    index = 0
    while index < len(paths):
        batch_paths = paths[index:index + FLUSH_BATCH_SIZE]
        batch = []
        for path in batch_paths:
            event = read_json_file(path)
            if not event:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            batch.append((path, event))
        index += FLUSH_BATCH_SIZE
        if not batch:
            continue
        stats["selected"] += len(batch)
        events = [event for _path, event in batch]
        ok, detail, status = send_events(
            settings["url"],
            settings["key_id"],
            settings["hmac_secret"],
            events,
            settings["timeout"],
        )
        if ok:
            for path, _event in batch:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            stats["sent"] += len(batch)
            continue
        if is_permanent_failure(status) and len(batch) > 1:
            should_stop = False
            for path, event in batch:
                item_ok, item_detail, item_status = send_event_with_status(
                    settings["url"],
                    settings["key_id"],
                    settings["hmac_secret"],
                    event,
                    settings["timeout"],
                )
                if item_ok:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                    stats["sent"] += 1
                    continue
                if is_permanent_failure(item_status):
                    dead_letter_event(event, item_detail)
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                    stats["dead_lettered"] += 1
                    continue
                stats["failed"] += 1
                should_stop = True
                if verbose:
                    print(f"telemetry queue flush failed: {item_detail}", file=sys.stderr)
                break
            if should_stop:
                break
            continue
        if is_permanent_failure(status):
            for path, event in batch:
                dead_letter_event(event, detail)
                try:
                    os.unlink(path)
                except OSError:
                    pass
            stats["dead_lettered"] += len(batch)
            continue
        stats["failed"] += len(batch)
        if verbose:
            print(f"telemetry queue flush failed: {detail}", file=sys.stderr)
        break
    return stats


def spawn_background(argv):
    child_args = [arg for arg in argv if arg != "--background"]
    env = os.environ.copy()
    env[BACKGROUND_ENV] = "1"
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), *child_args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def enqueue_current_event_if_configured(args):
    cfg = load_config()
    settings = telemetry_settings(cfg)
    if not is_configured(settings):
        return False
    return enqueue_event(build_event(args, cfg))


def emit(args):
    cfg = load_config()
    settings = telemetry_settings(cfg)

    if args.dry:
        event = build_event(args, cfg)
        print(json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if not is_configured(settings):
        if args.verbose:
            print("telemetry disabled or not configured", file=sys.stderr)
        return 0

    flush_queue(settings, verbose=args.verbose)
    event = build_event(args, cfg)
    ok, detail, status = send_event_with_status(
        settings["url"],
        settings["key_id"],
        settings["hmac_secret"],
        event,
        settings["timeout"],
    )
    if not ok and args.verbose:
        print(f"telemetry send failed: {detail}", file=sys.stderr)
    if not ok:
        if is_permanent_failure(status):
            dead_letter_event(event, detail)
        else:
            enqueue_event(event)
    if args.strict and not ok:
        return 1
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Send gerrit-pipeline telemetry")
    parser.add_argument("--event-type", default="pipeline_done", help="event type")
    parser.add_argument("--mode", default="unknown", help="pipeline mode, such as submit/amend/notify")
    parser.add_argument("--success", required=True, type=parse_bool, help="true or false")
    parser.add_argument("--duration-ms", default=0, type=int, help="pipeline duration in milliseconds")
    parser.add_argument("--repo-count", default=0, type=int, help="number of affected repositories")
    parser.add_argument("--error-code", default="", help="stable error code when success=false")
    parser.add_argument("--failure-stage", default="", help="failed pipeline stage, such as submit/review/checklist/notify")
    parser.add_argument("--agent", default="", help="agent runtime name")
    parser.add_argument("--submitter-name", default="", help="submitter display name")
    parser.add_argument("--event-id", default="", help="optional idempotency key")
    parser.add_argument("--background", action="store_true", help="spawn sender and return immediately")
    parser.add_argument("--dry", action="store_true", help="print payload without sending")
    parser.add_argument("--strict", action="store_true", help="return non-zero when sending fails")
    parser.add_argument("--verbose", action="store_true", help="print disabled/failure diagnostics")
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.background and os.environ.get(BACKGROUND_ENV) != "1" and not args.dry:
        spawned = spawn_background(argv)
        if not spawned:
            enqueue_current_event_if_configured(args)
        return 1 if args.strict and not spawned else 0
    return emit(args)


if __name__ == "__main__":
    raise SystemExit(main())
