#!/usr/bin/env bash
# Create a 24h one-time invite link for a named device, or list/revoke devices.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
exec .venv/bin/python add_device.py "$@"
