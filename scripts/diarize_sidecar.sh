#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"
source "$ROOT_DIR/scripts/lib/hf_token.sh"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required"
  exit 1
fi

if [[ $# -lt 1 ]]; then
  cat <<USAGE
Usage: $0 <audio-file> [--meeting-id <id>] [--job-id <job>] [--min-speakers N] [--max-speakers N] [--allow-transcript-without-diarization] [--no-diarization]
            [--transcript-json <json>]

Examples:
  $0 ~/Notes/audio/20260303-0959_Audio.wav --meeting-id m-abc123
  $0 ~/Notes/audio/20260303-0959_Audio.m4a --job-id test_run --allow-transcript-without-diarization
  $0 ~/Notes/audio/20260303-0959_Audio.m4a --transcript-json /path/to/transcript.json
USAGE
  exit 2
fi

INPUT_RAW="$1"
shift
INPUT_ABS="$(cd "$(dirname "$INPUT_RAW")" && pwd -P)/$(basename "$INPUT_RAW")"
if [[ ! -f "$INPUT_ABS" ]]; then
  echo "Input file not found: $INPUT_ABS"
  exit 1
fi

HOST_AUDIO_DIR="$(dirname "$INPUT_ABS")"
IN_CONTAINER_INPUT="/host_audio/$(basename "$INPUT_ABS")"
HOST_TRANSCRIPT_DIR="/tmp"
IN_CONTAINER_TRANSCRIPT_JSON=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --transcript-json)
      if [[ $# -lt 2 ]]; then
        echo "--transcript-json requires a path argument"
        exit 2
      fi
      TRANSCRIPT_RAW="$2"
      TRANSCRIPT_ABS="$(cd "$(dirname "$TRANSCRIPT_RAW")" && pwd -P)/$(basename "$TRANSCRIPT_RAW")"
      if [[ ! -f "$TRANSCRIPT_ABS" ]]; then
        echo "Transcript JSON not found: $TRANSCRIPT_ABS"
        exit 1
      fi
      HOST_TRANSCRIPT_DIR="$(dirname "$TRANSCRIPT_ABS")"
      IN_CONTAINER_TRANSCRIPT_JSON="/host_transcript/$(basename "$TRANSCRIPT_ABS")"
      EXTRA_ARGS+=("--transcript-json" "$IN_CONTAINER_TRANSCRIPT_JSON")
      shift 2
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

mkdir -p "$ROOT_DIR/shared_data/diarization/jobs"
mkdir -p "$ROOT_DIR/shared_data/diarization/cache/hf"
mkdir -p "$ROOT_DIR/shared_data/diarization/cache/transformers"
mkdir -p "$ROOT_DIR/shared_data/diarization/manifests"

export MEETINGCTL_HOST_AUDIO_PATH="$HOST_AUDIO_DIR"
export MEETINGCTL_HOST_TRANSCRIPT_PATH="$HOST_TRANSCRIPT_DIR"
export MEETINGCTL_ENV_PROFILE="${MEETINGCTL_ENV_PROFILE:-secure}"
meetingctl_load_env "$ROOT_DIR"
meetingctl_load_hf_token_from_file

needs_op_for_diarization=0
for key in HUGGINGFACE_TOKEN HF_TOKEN PYANNOTE_AUTH_TOKEN; do
  value="${!key:-}"
  if [[ "$value" == op://* ]]; then
    needs_op_for_diarization=1
    break
  fi
done

DOTENV_PATH="$(meetingctl_resolve_dotenv_path "$ROOT_DIR")"
if [[ "$needs_op_for_diarization" -eq 0 && -f "$DOTENV_PATH" ]]; then
  if rg -q '^[[:space:]]*(HUGGINGFACE_TOKEN|HF_TOKEN|PYANNOTE_AUTH_TOKEN)=.*op://' "$DOTENV_PATH"; then
    needs_op_for_diarization=1
  fi
fi

if [[ "$needs_op_for_diarization" -eq 1 ]]; then
  exec "$ROOT_DIR/scripts/secure_exec.sh" \
    docker compose -f "$ROOT_DIR/docker-compose.diarization.yml" run --rm diarizer \
    --input "$IN_CONTAINER_INPUT" "${EXTRA_ARGS[@]}"
fi

exec env MEETINGCTL_USE_1PASSWORD=0 \
  docker compose -f "$ROOT_DIR/docker-compose.diarization.yml" run --rm diarizer \
  --input "$IN_CONTAINER_INPUT" "${EXTRA_ARGS[@]}"
