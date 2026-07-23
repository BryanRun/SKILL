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
RUNS_DIR = os.path.join(CACHE_DIR, "runs")
LATEST_RUN_ID_PATH = os.path.join(RUNS_DIR, "latest")
DEFAULTS_PATH = os.path.join(SCRIPT_DIR, "telemetry_defaults.json")
INSTALL_ID_PATH = os.path.join(CONFIG_DIR, "install_id")
BACKGROUND_ENV = "GERRIT_PIPELINE_TELEMETRY_BACKGROUND"
SKILL_NAME = "gerrit-pipeline"
SCHEMA_VERSION = "1.1"
MAX_QUEUE_EVENTS = 200
MAX_DEAD_LETTER_EVENTS = 100
MAX_RUN_CONTEXTS = 200
FLUSH_BATCH_SIZE = 50
MAX_QUEUE_AGE_SECONDS = 14 * 24 * 60 * 60
MAX_RUN_CONTEXT_AGE_SECONDS = 14 * 24 * 60 * 60
PERMANENT_HTTP_STATUS = {400, 401, 403, 413}
FULL_PIPELINE_STEPS = ["submit", "review", "checklist", "notify", "meego_sync"]
STEP_DURATION_KEYS = {
    "submit": "submit_duration_s",
    "review": "review_duration_s",
    "checklist": "checklist_duration_s",
    "notify": "notify_duration_s",
    "meego_sync": "meego_sync_duration_s",
}
AGENT_ALIASES = {
    "claude": "claude-code",
    "claude_code": "claude-code",
    "claudecode": "claude-code",
    "claude-code": "claude-code",
    "codex": "codex",
    "cursor": "cursor",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "tongyi": "qwen",
    "dashscope": "qwen",
    "doubao": "doubao",
    "kimi": "kimi",
}

DEFAULT_TELEMETRY = {
    "enabled": True,
    "url": "http://10.70.55.96:18080",
    "key_id": "gerrit-pipeline-v2.1.0",
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


def normalize_agent(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace(" ", "-")
    return AGENT_ALIASES.get(text, text)


def detect_agent_from_process_tree():
    try:
        pid = os.getpid()
        for _ in range(8):
            output = subprocess.check_output(  # pragma: allowlist subprocess
                ["ps", "-o", "ppid=,comm=,args=", "-p", str(pid)],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if not output:
                break
            parts = output.split(None, 2)
            if not parts:
                break
            try:
                ppid = int(parts[0])
            except ValueError:
                break
            haystack = output.lower()
            for marker, agent in (
                ("claude", "claude-code"),
                ("codex", "codex"),
                ("cursor", "cursor"),
                ("deepseek", "deepseek"),
                ("qwen", "qwen"),
                ("tongyi", "qwen"),
                ("dashscope", "qwen"),
                ("doubao", "doubao"),
                ("kimi", "kimi"),
            ):
                if marker in haystack:
                    return agent
            if ppid <= 1 or ppid == pid:
                break
            pid = ppid
    except Exception:
        return ""
    return ""


def detect_agent_with_source():
    explicit = os.environ.get("GERRIT_PIPELINE_AGENT")
    if explicit:
        return normalize_agent(explicit), "env"
    if os.environ.get("CODEX_SANDBOX") or os.environ.get("CODEX_CLI"):
        return "codex", "env"
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE"):
        return "claude-code", "env"
    detected = detect_agent_from_process_tree()
    if detected:
        return detected, "process_tree"
    return "unknown", "fallback"


def detect_agent():
    agent, _source = detect_agent_with_source()
    return agent


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


def now_ms():
    return int(time.time() * 1000)


def ms_to_seconds(ms):
    try:
        return round(max(int(ms), 0) / 1000, 1)
    except (TypeError, ValueError):
        return 0.0


def seconds_value(value):
    try:
        return round(max(float(value), 0.0), 1)
    except (TypeError, ValueError):
        return 0.0


def parse_steps(value):
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value).strip()
        if not text:
            return []
        raw_items = re.split(r"[,>\s]+", text)
    steps = []
    for item in raw_items:
        step = str(item).strip().lower().replace("-", "_")
        if step and step not in steps:
            steps.append(step)
    return steps


def steps_to_string(steps):
    return ",".join(parse_steps(steps))


def is_full_pipeline_steps(steps):
    return parse_steps(steps) == FULL_PIPELINE_STEPS


def infer_mode(mode, steps):
    if mode and mode != "unknown":
        return mode
    parsed_steps = parse_steps(steps)
    if is_full_pipeline_steps(parsed_steps):
        return "full_pipeline"
    if len(parsed_steps) > 1:
        return "partial_pipeline"
    if len(parsed_steps) == 1:
        return "single_step"
    return "unknown"


def safe_run_id(value):
    text = str(value or "").strip()
    if text == "latest":
        return latest_run_id()
    if not text:
        return ""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", text)[:120]


def run_context_path(run_id):
    safe_id = safe_run_id(run_id)
    if not safe_id:
        return ""
    return os.path.join(RUNS_DIR, f"{safe_id}.json")


def load_run_context(run_id):
    path = run_context_path(run_id)
    if not path:
        return {}
    data = read_json_file(path)
    return data if isinstance(data, dict) else {}


def latest_run_id():
    try:
        with open(LATEST_RUN_ID_PATH, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if not text or text == "latest":
                return ""
            return re.sub(r"[^A-Za-z0-9_.-]", "_", text)[:120]
    except OSError:
        return ""


def write_latest_run_id(run_id):
    safe_id = safe_run_id(run_id)
    if not safe_id:
        return False
    try:
        os.makedirs(RUNS_DIR, mode=0o700, exist_ok=True)
        with open(LATEST_RUN_ID_PATH, "w", encoding="utf-8") as f:
            f.write(safe_id + "\n")
        return True
    except OSError:
        return False


def save_run_context(run_id, ctx):
    path = run_context_path(run_id)
    if not path:
        return False
    try:
        os.makedirs(RUNS_DIR, mode=0o700, exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(ctx, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
        write_latest_run_id(run_id)
        prune_run_contexts()
        return True
    except OSError:
        return False


def prune_run_contexts():
    try:
        paths = [
            os.path.join(RUNS_DIR, name)
            for name in os.listdir(RUNS_DIR)
            if name.endswith(".json")
        ]
    except OSError:
        return
    if not paths:
        return

    now = time.time()
    for path in paths:
        try:
            if now - os.path.getmtime(path) > MAX_RUN_CONTEXT_AGE_SECONDS:
                os.unlink(path)
        except OSError:
            pass

    try:
        paths = [
            os.path.join(RUNS_DIR, name)
            for name in os.listdir(RUNS_DIR)
            if name.endswith(".json")
        ]
    except OSError:
        return
    paths = sorted(paths, key=lambda path: (os.path.getmtime(path), path))
    overflow = len(paths) - MAX_RUN_CONTEXTS
    for path in paths[:max(0, overflow)]:
        try:
            os.unlink(path)
        except OSError:
            pass


def resolve_run_id(run_id):
    return safe_run_id(run_id) if run_id else latest_run_id()


def step_trace_entry(ctx, step):
    trace = ctx.setdefault("step_trace", [])
    if not isinstance(trace, list):
        trace = []
        ctx["step_trace"] = trace
    for item in reversed(trace):
        if isinstance(item, dict) and item.get("name") == step and not item.get("finished_at_ms"):
            return item
    item = {"name": step}
    trace.append(item)
    return item


def update_context_steps(ctx):
    steps = []
    for item in ctx.get("step_trace", []):
        if not isinstance(item, dict):
            continue
        step = str(item.get("name") or "")
        if step and step not in steps:
            steps.append(step)
    if steps:
        ctx["steps"] = steps
        ctx["is_full_pipeline"] = is_full_pipeline_steps(steps)
    durations = step_durations_from_trace(ctx.get("step_trace", []))
    if durations:
        ctx["step_durations"] = durations
    return ctx


def handle_run_context_command(args):
    if args.run_start:
        run_id = resolve_run_id(args.run_id) or str(uuid.uuid4())
        agent_source = "explicit" if args.agent else ""
        if args.agent:
            agent = normalize_agent(args.agent)
        else:
            agent, agent_source = detect_agent_with_source()
        steps = parse_steps(args.steps)
        ctx = {
            "run_id": run_id,
            "started_at": client_time(),
            "started_at_ms": now_ms(),
            "mode": infer_mode(args.mode, steps),
            "entry_mode": args.entry_mode or (steps[0] if steps else ""),
            "steps": steps,
            "is_full_pipeline": optional_bool(args.is_full_pipeline)
            if args.is_full_pipeline is not None else is_full_pipeline_steps(steps),
            "agent": agent,
            "agent_source": agent_source,
            "step_trace": [],
            "step_durations": {},
        }
        if not save_run_context(run_id, ctx):
            print("failed to save telemetry run context", file=sys.stderr)
            return 1
        print(run_id)
        return 0

    step_name = args.step_start or args.step_finish
    if not step_name:
        return None
    run_id = resolve_run_id(args.run_id)
    if not run_id:
        print("missing run context; pass --run-id or run --run-start first", file=sys.stderr)
        return 1
    ctx = load_run_context(run_id)
    if not ctx:
        print(f"run context not found: {run_id}", file=sys.stderr)
        return 1
    step = parse_steps(step_name)
    if not step:
        print("invalid step name", file=sys.stderr)
        return 1
    step = step[0]
    entry = step_trace_entry(ctx, step)
    if args.step_start:
        entry["started_at"] = client_time()
        entry["started_at_ms"] = now_ms()
    else:
        finished_ms = now_ms()
        entry.setdefault("started_at_ms", finished_ms)
        entry.setdefault("started_at", client_time())
        entry["finished_at"] = client_time()
        entry["finished_at_ms"] = finished_ms
        try:
            entry["duration_ms"] = max(finished_ms - int(entry["started_at_ms"]), 0)
        except (TypeError, ValueError):
            entry["duration_ms"] = 0
    update_context_steps(ctx)
    if not save_run_context(run_id, ctx):
        print("failed to save telemetry run context", file=sys.stderr)
        return 1
    print(run_id)
    return 0


def parse_step_durations(value):
    if not value:
        return {}
    if isinstance(value, dict):
        source = value
    else:
        text = str(value).strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            source = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            source = {}
            for item in text.split(","):
                if "=" not in item:
                    continue
                key, raw_value = item.split("=", 1)
                source[key.strip()] = raw_value.strip()
    durations = {}
    for key, raw_value in source.items():
        step = str(key).strip().lower().replace("-", "_")
        if not step:
            continue
        try:
            durations[step] = max(int(raw_value), 0)
        except (TypeError, ValueError):
            continue
    return durations


def step_durations_from_trace(trace):
    durations = {}
    if not isinstance(trace, list):
        return durations
    for item in trace:
        if not isinstance(item, dict):
            continue
        step = str(item.get("name") or "").strip().lower().replace("-", "_")
        if not step:
            continue
        duration = item.get("duration_ms")
        if duration is None and item.get("started_at_ms") is not None and item.get("finished_at_ms") is not None:
            try:
                duration = int(item["finished_at_ms"]) - int(item["started_at_ms"])
            except (TypeError, ValueError):
                duration = None
        if duration is None:
            continue
        try:
            durations[step] = max(int(duration), 0)
        except (TypeError, ValueError):
            continue
    return durations


def merge_step_durations(*items):
    merged = {}
    for item in items:
        merged.update(parse_step_durations(item))
    return merged


def step_trace_for_event(ctx, step_durations):
    trace = ctx.get("step_trace") if isinstance(ctx, dict) else None
    if isinstance(trace, list) and trace:
        normalized = []
        for item in trace:
            if not isinstance(item, dict):
                continue
            event_item = dict(item)
            duration_ms = event_item.pop("duration_ms", None)
            if event_item.get("duration_s") is None:
                if duration_ms is not None:
                    event_item["duration_s"] = ms_to_seconds(duration_ms)
                elif (
                    event_item.get("started_at_ms") is not None
                    and event_item.get("finished_at_ms") is not None
                ):
                    try:
                        event_item["duration_s"] = ms_to_seconds(
                            int(event_item["finished_at_ms"]) - int(event_item["started_at_ms"])
                        )
                    except (TypeError, ValueError):
                        event_item["duration_s"] = 0.0
            normalized.append(event_item)
        return normalized
    return [
        {"name": step, "duration_s": ms_to_seconds(duration)}
        for step, duration in step_durations.items()
    ]


def build_event(args, cfg):
    run_ctx = load_run_context(args.run_id) if getattr(args, "run_id", "") else {}
    ctx_steps = run_ctx.get("steps", [])
    arg_steps = parse_steps(getattr(args, "steps", ""))
    steps = arg_steps or parse_steps(ctx_steps)
    step_durations = merge_step_durations(
        step_durations_from_trace(run_ctx.get("step_trace", [])),
        run_ctx.get("step_durations", {}),
        getattr(args, "step_durations", ""),
    )
    entry_mode = (
        getattr(args, "entry_mode", "")
        or run_ctx.get("entry_mode", "")
        or (steps[0] if steps else "")
    )
    agent_source = "explicit" if getattr(args, "agent", "") else ""
    if getattr(args, "agent", ""):
        agent = normalize_agent(args.agent)
    elif run_ctx.get("agent"):
        agent = normalize_agent(run_ctx.get("agent"))
        agent_source = run_ctx.get("agent_source") or "run_context"
    else:
        agent, agent_source = detect_agent_with_source()
    duration_s = seconds_value(getattr(args, "duration_s", 0))
    duration_ms = max(int(getattr(args, "duration_ms", 0)), 0)
    if duration_s == 0 and duration_ms > 0:
        duration_s = ms_to_seconds(duration_ms)
    if duration_s == 0 and run_ctx.get("started_at_ms"):
        try:
            duration_s = ms_to_seconds(now_ms() - int(run_ctx["started_at_ms"]))
        except (TypeError, ValueError):
            duration_s = 0.0
    raw_mode = getattr(args, "mode", "unknown")
    if raw_mode == "unknown" and not steps and run_ctx.get("mode"):
        raw_mode = run_ctx.get("mode")
    mode = infer_mode(raw_mode, steps)
    is_full_pipeline = optional_bool(getattr(args, "is_full_pipeline", None))
    if is_full_pipeline is None and run_ctx.get("is_full_pipeline") is not None:
        is_full_pipeline = optional_bool(run_ctx.get("is_full_pipeline"))
    if is_full_pipeline is None:
        is_full_pipeline = is_full_pipeline_steps(steps)

    event = {
        "event_id": args.event_id or str(uuid.uuid4()),
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "skill_version": read_version(),
        "event_type": args.event_type,
        "mode": mode,
        "success": bool(args.success),
        "duration_s": duration_s,
        "repo_count": max(int(args.repo_count), 0),
        "client_time": client_time(),
        "agent": agent,
        "agent_source": agent_source,
        "install_id": get_install_id(cfg),
    }
    if entry_mode:
        event["entry_mode"] = entry_mode
    if steps:
        event["steps"] = steps_to_string(steps)
        event["is_full_pipeline"] = bool(is_full_pipeline)
    elif getattr(args, "is_full_pipeline", None) is not None:
        event["is_full_pipeline"] = bool(is_full_pipeline)
    if getattr(args, "run_id", ""):
        event["run_id"] = safe_run_id(args.run_id)
    for step, field in STEP_DURATION_KEYS.items():
        if step in step_durations:
            event[field] = ms_to_seconds(step_durations[step])
    trace = step_trace_for_event(run_ctx, step_durations)
    if trace:
        event["step_trace"] = json.dumps(trace, ensure_ascii=False, sort_keys=True)
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
        subprocess.Popen(  # pragma: allowlist subprocess
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
    parser.add_argument("--mode", default="unknown", help="pipeline type, such as full_pipeline/partial_pipeline/single_step")
    parser.add_argument("--entry-mode", default="", help="user entry mode, such as submit/amend/cherry-pick/notify")
    parser.add_argument("--steps", default="", help="actual executed steps in order, comma separated")
    parser.add_argument("--is-full-pipeline", default=None, type=optional_bool, help="whether the run completed the full pipeline")
    parser.add_argument("--success", default=None, type=parse_bool, help="true or false")
    parser.add_argument("--duration-s", default=0, type=float, help="pipeline duration in seconds")
    parser.add_argument("--duration-ms", default=0, type=int, help="legacy pipeline duration in milliseconds")
    parser.add_argument("--run-id", default="", help="run context id for cross-shell duration tracking")
    parser.add_argument("--run-start", action="store_true", help="create a run context and print its run id")
    parser.add_argument("--step-start", default="", help="mark a step start in the run context")
    parser.add_argument("--step-finish", default="", help="mark a step finish in the run context")
    parser.add_argument("--step-durations", default="", help="legacy step durations, JSON object or k=v comma list in milliseconds")
    parser.add_argument("--repo-count", default=0, type=int, help="number of affected repositories")
    parser.add_argument("--error-code", default="", help="stable error code when success=false")
    parser.add_argument("--failure-stage", default="", help="failed pipeline stage, such as submit/review/checklist/notify/meego_sync")
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
    run_rc = handle_run_context_command(args)
    if run_rc is not None:
        return run_rc
    if args.success is None:
        parser.error("--success is required when sending telemetry events")
    if args.background and os.environ.get(BACKGROUND_ENV) != "1" and not args.dry:
        spawned = spawn_background(argv)
        if not spawned:
            enqueue_current_event_if_configured(args)
        return 1 if args.strict and not spawned else 0
    return emit(args)


if __name__ == "__main__":
    raise SystemExit(main())
