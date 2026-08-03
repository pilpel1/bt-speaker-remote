#!/usr/bin/env bash
# Start BT Speaker Remote (reachable on LAN + Tailscale)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Prefer systemd when enabled (avoid double-start on same port)
if systemctl --user is-active --quiet bt-speaker-remote.service 2>/dev/null; then
  echo "Already running via systemd (bt-speaker-remote.service)"
  echo "Use: systemctl --user restart bt-speaker-remote.service"
  TS_IP="$(tailscale ip -4 2>/dev/null || true)"
  echo "  Local:     http://127.0.0.1:${BT_SPEAKER_PORT:-8765}"
  [[ -n "$TS_IP" ]] && echo "  Tailscale: http://${TS_IP}:${BT_SPEAKER_PORT:-8765}"
  exit 0
fi

# Load secrets / overrides from .env if present
if [[ -f "$DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$DIR/.env"
  set +a
fi

export BT_SPEAKER_HOST="${BT_SPEAKER_HOST:-0.0.0.0}"
export BT_SPEAKER_PORT="${BT_SPEAKER_PORT:-8765}"
# Ensure Pulse/PipeWire + D-Bus for this user session
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# Keep deps in sync (flask + waitress)
.venv/bin/pip install -q -r requirements.txt

mkdir -p "$DIR/logs"
PID_FILE="$DIR/logs/server.pid"
LOG_FILE="$DIR/logs/server.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Already running (pid $(cat "$PID_FILE"))"
  echo "Open: http://$(tailscale ip -4 2>/dev/null || echo 127.0.0.1):${BT_SPEAKER_PORT}"
  exit 0
fi

# Free port if a stale process holds it
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${BT_SPEAKER_PORT}/tcp" 2>/dev/null || true
fi

nohup .venv/bin/python server.py >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
sleep 0.8
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  TS_IP="$(tailscale ip -4 2>/dev/null || true)"
  echo "Started BT Speaker Remote (pid $(cat "$PID_FILE"))"
  echo "  Local:     http://127.0.0.1:${BT_SPEAKER_PORT}"
  if [[ -n "$TS_IP" ]]; then
    echo "  Tailscale: http://${TS_IP}:${BT_SPEAKER_PORT}"
  fi
  echo "  Log:       $LOG_FILE"
else
  echo "Failed to start — see $LOG_FILE" >&2
  exit 1
fi
