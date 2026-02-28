#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  echo "Missing .venv. Run install/setup first."
  exit 1
fi

export MEETINGCTL_ENV_PROFILE="${MEETINGCTL_ENV_PROFILE:-secure}"

exec "$ROOT_DIR/scripts/secure_exec.sh" \
  "$ROOT_DIR/.venv/bin/python" -m meetingctl.cli "$@"
