#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/load_dotenv.sh"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <audio-file-path>"
  exit 2
fi

INPUT_PATH="$1"
if [[ ! -f "$INPUT_PATH" ]]; then
  echo "hazel_ingest_file: input file not found: $INPUT_PATH"
  exit 1
fi

meetingctl_load_env "$ROOT_DIR"

RECORDINGS_ROOT="${RECORDINGS_PATH:-}"
if [[ -z "$RECORDINGS_ROOT" ]]; then
  echo "hazel_ingest_file: RECORDINGS_PATH is not set"
  exit 1
fi

RECORDINGS_ROOT="$(cd "$RECORDINGS_ROOT" && pwd -P)"
mkdir -p "$RECORDINGS_ROOT"

INPUT_ABS="$(cd "$(dirname "$INPUT_PATH")" && pwd -P)/$(basename "$INPUT_PATH")"
INPUT_EXT="${INPUT_ABS##*.}"
INPUT_EXT_LOWER="$(printf '%s' "$INPUT_EXT" | tr '[:upper:]' '[:lower:]')"

if [[ "$INPUT_EXT_LOWER" != "wav" && "$INPUT_EXT_LOWER" != "m4a" ]]; then
  echo "hazel_ingest_file: skipping unsupported extension: .$INPUT_EXT_LOWER"
  exit 0
fi

STAGED_PATH="$INPUT_ABS"
case "$INPUT_ABS" in
  "$RECORDINGS_ROOT"/*) ;;
  *)
    TARGET_BASENAME="$(basename "$INPUT_ABS")"
    TARGET_PATH="$RECORDINGS_ROOT/$TARGET_BASENAME"
    if [[ -e "$TARGET_PATH" ]]; then
      TARGET_STEM="${TARGET_BASENAME%.*}"
      TARGET_SUFFIX="${TARGET_BASENAME##*.}"
      TARGET_PATH="$RECORDINGS_ROOT/${TARGET_STEM}_$(date +%Y%m%d_%H%M%S).${TARGET_SUFFIX}"
    fi
    cp -f "$INPUT_ABS" "$TARGET_PATH"
    STAGED_PATH="$TARGET_PATH"
    echo "hazel_ingest_file: staged $INPUT_ABS -> $STAGED_PATH"
    ;;
esac

echo "hazel_ingest_file: triggering ingest for $STAGED_PATH"
bash "$ROOT_DIR/scripts/run_ingest_once.sh"
