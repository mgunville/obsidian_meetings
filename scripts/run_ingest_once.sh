#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/load_dotenv.sh"

STATE_DIR="${MEETINGCTL_AUTOMATION_STATE_DIR:-$HOME/.local/state/meetingctl}"
LOCK_DIR="${MEETINGCTL_AUTOMATION_LOCK_DIR:-$STATE_DIR/automation_ingest.lock}"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR" 2>/dev/null || true
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

meetingctl_load_env "$ROOT_DIR"

export PYTHONPATH=src

# Single-pass ingest for file-triggered automation (Hazel/KM).
python -m meetingctl.cli ingest-watch --once --match-calendar --json

# Drain queue in batches so a single Hazel trigger can fully process backlog.
QUEUE_BATCH_SIZE="${MEETINGCTL_PROCESS_QUEUE_MAX_JOBS:-3}"
QUEUE_DRAIN_PASSES="${MEETINGCTL_PROCESS_QUEUE_DRAIN_PASSES:-6}"
QUEUE_FAILURE_MODE="${MEETINGCTL_PROCESS_QUEUE_FAILURE_MODE:-dead_letter}"
pass=1
while [[ "$pass" -le "$QUEUE_DRAIN_PASSES" ]]; do
  process_output="$(python -m meetingctl.cli process-queue --max-jobs "$QUEUE_BATCH_SIZE" --json)"
  echo "$process_output"

  failed_jobs="$(printf '%s' "$process_output" | python -c 'import json,sys; p=json.loads(sys.stdin.read() or "{}"); print(int(p.get("failed_jobs", 0)))')"
  remaining_jobs="$(printf '%s' "$process_output" | python -c 'import json,sys; p=json.loads(sys.stdin.read() or "{}"); print(int(p.get("remaining_jobs", 0)))')"

  if [[ "$remaining_jobs" -eq 0 ]]; then
    break
  fi
  if [[ "$failed_jobs" -gt 0 && "$QUEUE_FAILURE_MODE" == "stop" ]]; then
    break
  fi
  pass=$((pass + 1))
done

# Optional metadata normalization for moved/new meeting notes.
if [[ "${MEETINGCTL_NORMALIZE_FRONTMATTER:-0}" == "1" ]]; then
  python -m meetingctl.cli normalize-frontmatter \
    --scope "${MEETINGCTL_NORMALIZE_SCOPE:-_Work}" \
    --json
fi
