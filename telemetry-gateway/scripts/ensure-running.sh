#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$BASE_DIR/logs/telemetry-gateway.pid"
LOG_FILE="$BASE_DIR/logs/telemetry-gateway.log"
ENV_FILE="$BASE_DIR/.env"

mkdir -p "$BASE_DIR/logs" "$BASE_DIR/data"

env_value() {
  local key="$1" default="$2"
  local value="${!key:-}"
  if [[ -z "$value" && -f "$ENV_FILE" ]]; then
    value="$(python3 - "$ENV_FILE" "$key" <<'PY'
import sys
from pathlib import Path

env_file = Path(sys.argv[1])
target = sys.argv[2]
for raw in env_file.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == target:
        print(value.strip().strip('"').strip("'"))
        break
PY
)"
  fi
  printf '%s' "${value:-$default}"
}

health_url() {
  local host port
  host="$(env_value TELEMETRY_HOST 127.0.0.1)"
  port="$(env_value TELEMETRY_PORT 18080)"
  if [[ "$host" == "0.0.0.0" || "$host" == "::" ]]; then
    host="127.0.0.1"
  fi
  printf 'http://%s:%s/healthz' "$host" "$port"
}

is_healthy() {
  local url="$1"
  python3 - "$url" <<'PY'
import json
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as resp:
        if resp.status != 200:
            raise SystemExit(1)
        body = json.loads(resp.read().decode("utf-8"))
        raise SystemExit(0 if body.get("ok") else 1)
except Exception:
    raise SystemExit(1)
PY
}

stop_stale_pid() {
  local pid="$1"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "telemetry-gateway pid=$pid is not healthy; restarting" >>"$LOG_FILE"
    kill "$pid" 2>/dev/null || true
    for _ in {1..10}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$PID_FILE"
}

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    if is_healthy "$(health_url)"; then
      exit 0
    fi
    stop_stale_pid "$pid"
  else
    rm -f "$PID_FILE"
  fi
fi

cd "$BASE_DIR"
nohup python3 app.py >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

for _ in {1..20}; do
  if is_healthy "$(health_url)"; then
    exit 0
  fi
  sleep 0.2
done

echo "telemetry-gateway started but health check did not pass" >>"$LOG_FILE"
exit 1
