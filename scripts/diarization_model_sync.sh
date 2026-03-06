#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"
source "$ROOT_DIR/scripts/lib/dotenv_set.sh"
source "$ROOT_DIR/scripts/lib/hf_token.sh"

export MEETINGCTL_ENV_PROFILE="${MEETINGCTL_ENV_PROFILE:-secure}"
meetingctl_load_env "$ROOT_DIR"
meetingctl_load_hf_token_from_file

if "$ROOT_DIR/scripts/secure_exec.sh" \
  env WHISPERX_OFFLINE_MODE=0 \
  docker compose -f "$ROOT_DIR/docker-compose.diarization.yml" run --rm --entrypoint python diarizer \
  /workspace/scripts/diarization_model_sync.py "$@"; then
  DOTENV_PATH="${MEETINGCTL_DIARIZATION_MODEL_DOTENV_PATH:-$ROOT_DIR/.env}"
  if [[ "$DOTENV_PATH" == "~/"* ]]; then
    DOTENV_PATH="$HOME/${DOTENV_PATH#"~/"}"
  fi
  now_iso="$(python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat().replace("+00:00","Z"))
PY
)"
  dotenv_set_key "$DOTENV_PATH" "MEETINGCTL_DIARIZATION_MODEL_LAST_CHECK_AT" "$now_iso"
  dotenv_set_key "$DOTENV_PATH" "MEETINGCTL_DIARIZATION_MODEL_LAUNCH_COUNT_SINCE_CHECK" "0"
  exit 0
fi

exit 1
