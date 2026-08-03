#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/logs/server.pid"
if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    sleep 0.5
    kill -9 "$PID" 2>/dev/null || true
    echo "Stopped pid $PID"
  else
    echo "Not running"
  fi
  rm -f "$PID_FILE"
else
  echo "No pid file"
fi
# Also stop any leftover player
pkill -f "mpv --no-video" 2>/dev/null || true
