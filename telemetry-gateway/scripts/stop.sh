#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$BASE_DIR/logs/telemetry-gateway.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "telemetry-gateway is not running (pid file missing)"
  exit 0
fi

pid="$(cat "$PID_FILE")"
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  for _ in {1..10}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  echo "stopped telemetry-gateway pid=$pid"
else
  echo "telemetry-gateway pid=$pid is not alive"
fi
rm -f "$PID_FILE"
