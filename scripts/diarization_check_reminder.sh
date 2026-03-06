#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"
source "$ROOT_DIR/scripts/lib/dotenv_set.sh"

meetingctl_load_env "$ROOT_DIR"
DOTENV_PATH="${MEETINGCTL_DIARIZATION_MODEL_DOTENV_PATH:-$ROOT_DIR/.env}"
if [[ "$DOTENV_PATH" == "~/"* ]]; then
  DOTENV_PATH="$HOME/${DOTENV_PATH#"~/"}"
fi

if [[ -f "$DOTENV_PATH" ]]; then
  load_dotenv_file "$DOTENV_PATH"
fi

enabled_raw="${MEETINGCTL_DIARIZATION_MODEL_CHECK_REMINDER:-1}"
enabled="$(printf '%s' "$enabled_raw" | tr '[:upper:]' '[:lower:]')"
if [[ "$enabled" == "0" || "$enabled" == "false" || "$enabled" == "no" || "$enabled" == "off" ]]; then
  exit 0
fi

last_check_at="${MEETINGCTL_DIARIZATION_MODEL_LAST_CHECK_AT:-}"
interval_days="${MEETINGCTL_DIARIZATION_MODEL_CHECK_INTERVAL_DAYS:-30}"
interval_launches="${MEETINGCTL_DIARIZATION_MODEL_CHECK_INTERVAL_LAUNCHES:-180}"
launch_count="${MEETINGCTL_DIARIZATION_MODEL_LAUNCH_COUNT_SINCE_CHECK:-0}"

if ! [[ "$interval_days" =~ ^[0-9]+$ ]]; then
  interval_days=30
fi
if ! [[ "$interval_launches" =~ ^[0-9]+$ ]]; then
  interval_launches=180
fi
if ! [[ "$launch_count" =~ ^[0-9]+$ ]]; then
  launch_count=0
fi

launch_count=$((launch_count + 1))
if [[ -f "$DOTENV_PATH" ]]; then
  dotenv_set_key "$DOTENV_PATH" "MEETINGCTL_DIARIZATION_MODEL_LAUNCH_COUNT_SINCE_CHECK" "$launch_count"
fi

days_since=-1
if [[ -n "$last_check_at" ]]; then
  days_since="$(python3 - "$last_check_at" <<'PY'
from datetime import datetime, timezone
import sys

value = sys.argv[1].strip()
try:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
except ValueError:
    print(-1)
    raise SystemExit(0)
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
delta = now - dt.astimezone(timezone.utc)
print(max(delta.days, 0))
PY
)"
fi

due_by_days=0
if [[ "$interval_days" -gt 0 ]]; then
  if [[ -z "$last_check_at" || "$days_since" -lt 0 || "$days_since" -ge "$interval_days" ]]; then
    due_by_days=1
  fi
fi

due_by_launches=0
if [[ "$interval_launches" -gt 0 && "$launch_count" -ge "$interval_launches" ]]; then
  due_by_launches=1
fi

if [[ "$due_by_days" -eq 1 || "$due_by_launches" -eq 1 ]]; then
  echo "diarization-model-check: due (last_check_at='${last_check_at:-unset}', launches_since_check=$launch_count, interval_days=$interval_days, interval_launches=$interval_launches)."
  echo "diarization-model-check: run 'MEETINGCTL_ENV_PROFILE=secure bash $ROOT_DIR/scripts/diarization_model_sync.sh --json' (or --refresh --json)."
fi
