#!/usr/bin/env bash
set -uo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export BASE_DIR

python3 - <<'PY'
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


base_dir = Path(os.environ["BASE_DIR"])
env_file = base_dir / ".env"
pid_file = base_dir / "logs" / "telemetry-gateway.pid"
log_file = base_dir / "logs" / "telemetry-gateway.log"


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def request_json(url: str, token: str = "", method: str = "GET") -> tuple[int, object]:
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:
        return 0, {"ok": False, "error": type(exc).__name__, "detail": str(exc)}


def print_json(prefix: str, status: int, body: object) -> bool:
    ok = isinstance(body, dict) and body.get("ok") is True and 200 <= status < 300
    marker = "OK" if ok else "FAIL"
    print(f"{prefix}: {marker} http={status}")
    if isinstance(body, dict):
        for key in (
            "ok",
            "error",
            "detail",
            "service",
            "version",
            "server_version",
            "bitable_configured",
            "dry_run",
            "field_count",
            "db_path",
        ):
            if key in body:
                print(f"  {key}: {body[key]}")
        if "counts" in body:
            counts = body.get("counts") or {}
            rendered = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            print(f"  counts: {rendered or '{}'}")
    else:
        print(f"  body: {str(body)[:300]}")
    return ok


env = read_env(env_file)
host = env.get("TELEMETRY_HOST", "127.0.0.1")
port = env.get("TELEMETRY_PORT", "18080")
health_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
base_url = f"http://{health_host}:{port}"
admin_token = env.get("TELEMETRY_ADMIN_TOKEN", "")
db_path = env.get("TELEMETRY_DB_PATH", str(base_dir / "data" / "telemetry.sqlite3"))

print("Telemetry Gateway Status")
print(f"base_dir: {base_dir}")
print(f"endpoint: {base_url}")
print(f"env_file: {env_file} ({'present' if env_file.exists() else 'missing'})")
print(f"db_path: {db_path}")
print(f"log_file: {log_file}")
print(f"admin_token: {'configured' if admin_token else 'missing'}")

print("\nProcess")
pid_ok = False
if pid_file.exists():
    raw_pid = pid_file.read_text(encoding="utf-8").strip()
    try:
        pid = int(raw_pid)
        pid_ok = is_alive(pid)
        print(f"pid_file: {pid_file}")
        print(f"pid: {pid} ({'alive' if pid_ok else 'not alive'})")
        if pid_ok:
            ps = subprocess.run(
                ["ps", "-p", str(pid), "-o", "pid,ppid,etime,cmd"],
                check=False,
                text=True,
                capture_output=True,
            )
            print(ps.stdout.rstrip())
            cwd_link = Path(f"/proc/{pid}/cwd")
            if cwd_link.exists():
                print(f"cwd: {cwd_link.resolve()}")
    except ValueError:
        print(f"pid_file: {pid_file} (invalid: {raw_pid!r})")
else:
    print(f"pid_file: {pid_file} (missing)")

print("\nHTTP")
health_status, health_body = request_json(f"{base_url}/healthz")
health_ok = print_json("healthz", health_status, health_body)

ready_ok = True
metrics_ok = True
if admin_token:
    version_status, version_body = request_json(f"{base_url}/version", admin_token)
    version_ok = print_json("version", version_status, version_body)
    ready_status, ready_body = request_json(f"{base_url}/readyz", admin_token)
    ready_ok = print_json("readyz", ready_status, ready_body)
    metrics_status, metrics_body = request_json(f"{base_url}/metrics", admin_token)
    metrics_ok = print_json("metrics", metrics_status, metrics_body)
else:
    version_ok = True
    print("version: SKIP admin token missing")
    print("readyz: SKIP admin token missing")
    print("metrics: SKIP admin token missing")

print("\nRecent Log Warnings")
if log_file.exists():
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    pattern = re.compile(r"(ERROR|WARN|Traceback|failed|exception)", re.IGNORECASE)
    matches = [line for line in lines[-300:] if pattern.search(line)]
    if matches:
        for line in matches[-8:]:
            print(line)
    else:
        print("none in last 300 log lines")
else:
    print("log file missing")

if health_ok and version_ok and ready_ok and metrics_ok:
    sys.exit(0)
sys.exit(1)
PY
