#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Run scripts/setup.sh first."
  exit 1
fi

source .venv/bin/activate
export PYTHONPATH="${PYTHONPATH:-}:$ROOT_DIR/src"
export MEETINGCTL_ENV_PROFILE="${MEETINGCTL_ENV_PROFILE:-secure}"
export MEETINGCTL_DIARIZATION_INSECURE_SSL="${MEETINGCTL_DIARIZATION_INSECURE_SSL:-1}"
export WHISPERX_OFFLINE_MODE="${WHISPERX_OFFLINE_MODE:-0}"

exec bash "$ROOT_DIR/scripts/secure_exec.sh" \
  ./.venv/bin/python "$ROOT_DIR/scripts/diarization_catchup.py" \
  --prefer-existing-transcript-json \
  --require-existing-transcript-json \
  --require-pyannote \
  --replace-active \
  --json \
  "$@"
