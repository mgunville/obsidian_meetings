#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INTERVAL_SECONDS=30
RUN_ONCE=0

usage() {
  cat <<'USAGE'
Usage: scripts/monitor_progress.sh [--interval <seconds>] [--once]

Examples:
  scripts/monitor_progress.sh
  scripts/monitor_progress.sh --interval 10
  scripts/monitor_progress.sh --once
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval)
      if [[ $# -lt 2 ]]; then
        echo "--interval requires a value"
        exit 2
      fi
      INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --once)
      RUN_ONCE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

if ! [[ "$INTERVAL_SECONDS" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_SECONDS" -lt 1 ]]; then
  echo "Invalid --interval value: $INTERVAL_SECONDS"
  exit 2
fi

QUEUE_FILE="${MEETINGCTL_PROCESS_QUEUE_FILE:-$HOME/.local/state/meetingctl/process_queue.jsonl}"
PROCESSED_FILE="${MEETINGCTL_PROCESSED_JOBS_FILE:-$HOME/.local/state/meetingctl/processed_jobs.jsonl}"
DEADLETTER_FILE="${MEETINGCTL_PROCESS_QUEUE_DEAD_LETTER_FILE:-$HOME/.local/state/meetingctl/process_queue.deadletter.jsonl}"
DIARIZATION_JOBS_DIR="$ROOT_DIR/shared_data/diarization/jobs"
DIARIZATION_MANIFESTS_DIR="$ROOT_DIR/shared_data/diarization/manifests"

PYTHON_BIN=""
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "No Python interpreter found (checked .venv/bin/python, python3, python)."
  exit 1
fi

line_count() {
  local path="$1"
  if [[ -f "$path" ]]; then
    wc -l < "$path" | tr -d ' '
  else
    echo "0"
  fi
}

parse_etime_to_seconds() {
  local etime="$1"
  local days=0
  local hms="$etime"
  if [[ "$etime" == *-* ]]; then
    days="${etime%%-*}"
    hms="${etime#*-}"
  fi
  IFS=':' read -r a b c <<<"$hms"
  if [[ -z "${c:-}" ]]; then
    c="$b"
    b="$a"
    a=0
  fi
  echo $((days * 86400 + a * 3600 + b * 60 + c))
}

format_duration() {
  local total="$1"
  if [[ "$total" -lt 0 ]]; then
    total=0
  fi
  local h=$((total / 3600))
  local m=$(((total % 3600) / 60))
  local s=$((total % 60))
  printf '%02d:%02d:%02d' "$h" "$m" "$s"
}

latest_dry_run_target() {
  "$PYTHON_BIN" - "$DIARIZATION_MANIFESTS_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
if not root.exists():
    print("0")
    raise SystemExit(0)

for path in sorted(root.glob("catchup_*.json"), reverse=True):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if not payload.get("dry_run", False):
        continue
    results = payload.get("results", [])
    if not isinstance(results, list):
        continue
    target = sum(1 for item in results if isinstance(item, dict) and not item.get("skipped", False))
    print(str(target))
    raise SystemExit(0)

print("0")
PY
}

count_completed_jobs_since_epoch() {
  local start_epoch="$1"
  "$PYTHON_BIN" - "$DIARIZATION_JOBS_DIR" "$start_epoch" <<'PY'
import sys
from pathlib import Path

jobs_dir = Path(sys.argv[1])
start_epoch = float(sys.argv[2])

if not jobs_dir.exists():
    print("0")
    raise SystemExit(0)

count = 0
for job_dir in jobs_dir.iterdir():
    if not job_dir.is_dir():
        continue
    manifest = job_dir / "manifest.json"
    if not manifest.exists():
        continue
    if manifest.stat().st_mtime >= start_epoch:
        count += 1
print(str(count))
PY
}

active_diarizer_status() {
  local cid
  cid="$(docker ps -q --filter ancestor=meetingctl-diarizer:local | head -1 || true)"
  if [[ -z "$cid" ]]; then
    echo "idle|"
    return
  fi
  local status current
  status="$(docker ps --filter id="$cid" --format '{{.Status}}' | head -1)"
  current="$(docker top "$cid" 2>/dev/null | awk 'NR==2{for (i=8; i<=NF; i++) printf $i " "; print ""}' | sed 's/[[:space:]]*$//')"
  echo "${status}|${current}"
}

TARGET_TOTAL="$(latest_dry_run_target)"

print_snapshot() {
  local now queue_count processed_count failed_count
  now="$(date '+%Y-%m-%d %H:%M:%S')"
  queue_count="$(line_count "$QUEUE_FILE")"
  processed_count="$(line_count "$PROCESSED_FILE")"
  failed_count="$(line_count "$DEADLETTER_FILE")"

  local catchup_pid catchup_etime catchup_elapsed catchup_start_epoch completed_since_start
  catchup_pid="$(pgrep -f "scripts/diarization_catchup.py" | head -1 || true)"
  catchup_etime=""
  catchup_elapsed=0
  catchup_start_epoch=0
  completed_since_start=0
  if [[ -n "$catchup_pid" ]]; then
    catchup_etime="$(ps -p "$catchup_pid" -o etime= | xargs)"
    catchup_elapsed="$(parse_etime_to_seconds "${catchup_etime:-0:00}")"
    catchup_start_epoch="$(( $(date +%s) - catchup_elapsed ))"
    completed_since_start="$(count_completed_jobs_since_epoch "$catchup_start_epoch")"
  fi

  local diarizer_status status_field current_field
  diarizer_status="$(active_diarizer_status)"
  status_field="${diarizer_status%%|*}"
  current_field="${diarizer_status#*|}"

  local eta="unknown"
  if [[ -n "$catchup_pid" ]] && [[ "$TARGET_TOTAL" -gt 0 ]] && [[ "$completed_since_start" -gt 0 ]] && [[ "$catchup_elapsed" -gt 0 ]]; then
    local sec_per_item remaining eta_seconds
    sec_per_item=$((catchup_elapsed / completed_since_start))
    if [[ "$sec_per_item" -lt 1 ]]; then
      sec_per_item=1
    fi
    remaining=$((TARGET_TOTAL - completed_since_start))
    if [[ "$remaining" -lt 0 ]]; then
      remaining=0
    fi
    eta_seconds=$((remaining * sec_per_item))
    eta="$(format_duration "$eta_seconds")"
  fi

  echo "$now queue=$queue_count processed_total=$processed_count deadletter=$failed_count target=${TARGET_TOTAL:-0}"
  if [[ -n "$catchup_pid" ]]; then
    echo "  catchup_pid=$catchup_pid elapsed=$(format_duration "$catchup_elapsed") completed_since_start=$completed_since_start eta=$eta"
  else
    echo "  catchup_pid=none"
  fi
  echo "  diarizer_status=${status_field:-idle}"
  echo "  diarizer_current=${current_field:--}"
}

while true; do
  print_snapshot
  if [[ "$RUN_ONCE" -eq 1 ]]; then
    exit 0
  fi
  sleep "$INTERVAL_SECONDS"
done
