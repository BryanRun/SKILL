#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$BASE_DIR/logs/telemetry-gateway.pid"
cd "$BASE_DIR"

local_pid_alive() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

endpoint_healthy() {
  python3 - "$BASE_DIR/.env" <<'PY'
import json
import sys
import urllib.request
from pathlib import Path

env_file = Path(sys.argv[1])
values = {}
if env_file.exists():
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

host = values.get("TELEMETRY_HOST", "127.0.0.1")
if host in {"0.0.0.0", "::"}:
    host = "127.0.0.1"
port = values.get("TELEMETRY_PORT", "18080")
try:
    with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=3) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        raise SystemExit(0 if resp.status == 200 and body.get("ok") else 1)
except Exception:
    raise SystemExit(1)
PY
}

if ! local_pid_alive && endpoint_healthy; then
  echo "telemetry-gateway endpoint is healthy, but no live pid belongs to $BASE_DIR"
  echo "Refusing to restart from this directory. Run restart.sh in the deployed gateway directory."
  exit 1
fi

./scripts/stop.sh
./scripts/ensure-running.sh
./scripts/status.sh
