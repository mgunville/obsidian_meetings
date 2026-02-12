#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Run install/setup first."
  exit 1
fi

source .venv/bin/activate

if [[ -f ".env" ]]; then
  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    line="${raw_line#"${raw_line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    if [[ -z "$line" || "$line" == \#* ]]; then
      continue
    fi
    if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      key="${line%%=*}"
      value="${line#*=}"
      if [[ "$value" =~ ^\".*\"$ ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "$value" =~ ^\'.*\'$ ]]; then
        value="${value:1:${#value}-2}"
      fi
      export "$key=$value"
    fi
  done < .env
fi

export PYTHONPATH=src

WINDOW_MINUTES="${MEETINGCTL_MATCH_WINDOW_MINUTES:-30}"
EXTENSIONS="${MEETINGCTL_BACKFILL_EXTENSIONS:-wav,m4a}"
DRY_RUN=1
EXTRA_ARGS=()
HAS_EXTENSIONS_ARG=0
HAS_WINDOW_ARG=0
HAS_MATCH_CALENDAR_ARG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      DRY_RUN=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --extensions)
      HAS_EXTENSIONS_ARG=1
      EXTRA_ARGS+=("$1")
      shift
      if [[ $# -gt 0 ]]; then
        EXTRA_ARGS+=("$1")
        shift
      fi
      ;;
    --window-minutes)
      HAS_WINDOW_ARG=1
      EXTRA_ARGS+=("$1")
      shift
      if [[ $# -gt 0 ]]; then
        EXTRA_ARGS+=("$1")
        shift
      fi
      ;;
    --match-calendar)
      HAS_MATCH_CALENDAR_ARG=1
      EXTRA_ARGS+=("$1")
      shift
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

CMD=(python -m meetingctl.cli backfill --json)

if [[ "$HAS_EXTENSIONS_ARG" -eq 0 ]]; then
  CMD+=(--extensions "$EXTENSIONS")
fi
if [[ "$HAS_MATCH_CALENDAR_ARG" -eq 0 ]]; then
  CMD+=(--match-calendar)
fi
if [[ "$HAS_WINDOW_ARG" -eq 0 ]]; then
  CMD+=(--window-minutes "$WINDOW_MINUTES")
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  CMD+=(--dry-run)
fi

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  CMD+=("${EXTRA_ARGS[@]}")
fi

echo "Running: ${CMD[*]}"
"${CMD[@]}"
