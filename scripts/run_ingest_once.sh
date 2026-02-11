#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STATE_DIR="${MEETINGCTL_AUTOMATION_STATE_DIR:-$HOME/.local/state/meetingctl}"
LOCK_DIR="${MEETINGCTL_AUTOMATION_LOCK_DIR:-$STATE_DIR/automation_ingest.lock}"
mkdir -p "$STATE_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "run_ingest_once: lock held at $LOCK_DIR; skipping duplicate trigger"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Run install/setup first."
  exit 1
fi

source .venv/bin/activate

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PYTHONPATH=src

# Single-pass ingest + queue processing for file-triggered automation (Hazel/KM).
python -m meetingctl.cli ingest-watch --once --match-calendar --json
python -m meetingctl.cli process-queue --json
