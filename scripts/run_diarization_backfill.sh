#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"
source "$ROOT_DIR/scripts/lib/hf_token.sh"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Run scripts/setup.sh first."
  exit 1
fi

source .venv/bin/activate
export PYTHONPATH="${PYTHONPATH:-}:$ROOT_DIR/src"
export MEETINGCTL_ENV_PROFILE="${MEETINGCTL_ENV_PROFILE:-secure}"
export MEETINGCTL_DIARIZATION_INSECURE_SSL="${MEETINGCTL_DIARIZATION_INSECURE_SSL:-1}"
export WHISPERX_OFFLINE_MODE="${WHISPERX_OFFLINE_MODE:-0}"
meetingctl_load_env "$ROOT_DIR"
meetingctl_load_hf_token_from_file

exec ./.venv/bin/python "$ROOT_DIR/scripts/diarization_catchup.py" \
  --prefer-existing-transcript-json \
  --require-existing-transcript-json \
  --require-pyannote \
  --replace-active \
  --json \
  "$@"
