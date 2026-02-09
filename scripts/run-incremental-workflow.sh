#!/bin/bash
# ABOUTME: Runs incremental meetingctl workflow checks end-to-end.
# ABOUTME: Supports safe local mode and real-machine mode.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
MODE="${MODE:-local}"  # local|real
STATE_DIR="${STATE_DIR:-/tmp/meetingctl-incremental-$$}"
QUEUE_FILE="$STATE_DIR/process_queue.jsonl"
PROCESSED_FILE="$STATE_DIR/processed_jobs.jsonl"
NOW_ISO="${NOW_ISO:-2026-02-08T10:05:00+00:00}"

cleanup() {
  rm -rf "$STATE_DIR"
}
trap cleanup EXIT

mkdir -p "$STATE_DIR"

export PYTHONPATH="$PROJECT_ROOT/src"
export MEETINGCTL_STATE_FILE="$STATE_DIR/current.json"
export MEETINGCTL_PROCESS_QUEUE_FILE="$QUEUE_FILE"
export MEETINGCTL_PROCESSED_JOBS_FILE="$PROCESSED_FILE"

if [ "$MODE" = "local" ]; then
  export MEETINGCTL_NOW_ISO="$NOW_ISO"
  export MEETINGCTL_RECORDING_DRY_RUN=1
  export MEETINGCTL_EVENTKIT_EVENTS_JSON='[{"title":"Incremental Event","start":"2026-02-08T10:00:00+00:00","end":"2026-02-08T10:30:00+00:00","calendar_name":"Work","location":"https://teams.microsoft.com/l/meetup-join/abc"}]'
  export MEETINGCTL_PROCESSING_SUMMARY_JSON='{"minutes":"Dry-run summary","decisions":["Decision"],"action_items":["Action"]}'
  export MEETINGCTL_PROCESSING_CONVERT_DRY_RUN=1
  echo "[info] running in local mode (dry-run recorder + seeded event payload)"
else
  unset MEETINGCTL_NOW_ISO || true
  echo "[info] running in real mode (real recorder/calendar integrations)"
fi

run_cli() {
  "$PYTHON_BIN" -m meetingctl.cli "$@"
}

echo "== doctor =="
run_cli doctor --json

echo "== event =="
run_cli event --now-or-next 5 --json

echo "== start (calendar-driven) =="
run_cli start --json

echo "== status active =="
run_cli status --json

echo "== stop =="
STOP_JSON="$(run_cli stop --json)"
echo "$STOP_JSON"

if [ "$MODE" = "local" ]; then
  MEETING_ID="$("$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin).get("meeting_id",""))' <<<"$STOP_JSON")"
  RECORDINGS_ROOT="${RECORDINGS_PATH:-$STATE_DIR/recordings}"
  mkdir -p "$RECORDINGS_ROOT"
  if [ -n "$MEETING_ID" ]; then
    printf "fake-wav" >"$RECORDINGS_ROOT/$MEETING_ID.wav"
    printf "fake transcript" >"$RECORDINGS_ROOT/$MEETING_ID.txt"
  fi
fi

echo "== process queue =="
run_cli process-queue --max-jobs 10 --json

echo "== status idle =="
run_cli status --json

echo "[ok] incremental workflow completed"
