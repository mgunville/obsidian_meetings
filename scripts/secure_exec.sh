#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"

if [[ "$#" -lt 1 ]]; then
  echo "Usage: $0 <command> [args...]"
  exit 2
fi

if [[ -z "${MEETINGCTL_ENV_PROFILE:-}" ]]; then
  target_script=""
  if [[ "$#" -ge 2 && ( "$1" == "bash" || "$1" == "/bin/bash" || "$1" == "zsh" || "$1" == "/bin/zsh" ) ]]; then
    target_script="$(basename "$2")"
  else
    target_script="$(basename "$1")"
  fi
  if [[ "$target_script" == "hazel_ingest_file.sh" || "$target_script" == "run_ingest_once.sh" ]]; then
    export MEETINGCTL_ENV_PROFILE="dev"
  fi
fi

DOTENV_PATH="$(meetingctl_resolve_dotenv_path "$ROOT_DIR")"
USE_1PASSWORD="${MEETINGCTL_USE_1PASSWORD:-}"
if [[ -z "$USE_1PASSWORD" && -f "$DOTENV_PATH" ]]; then
  file_use_1password="$(awk -F= '/^MEETINGCTL_USE_1PASSWORD=/{print $2; exit}' "$DOTENV_PATH" | tr -d '"' | tr -d "'" | xargs)"
  USE_1PASSWORD="${file_use_1password:-auto}"
fi
USE_1PASSWORD="${USE_1PASSWORD:-auto}"
NEEDS_OP=0

resolve_op_binary() {
  if command -v op >/dev/null 2>&1; then
    command -v op
    return 0
  fi
  for candidate in /opt/homebrew/bin/op /usr/local/bin/op; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if [[ -f "$DOTENV_PATH" ]]; then
  if [[ "$USE_1PASSWORD" == "1" ]]; then
    NEEDS_OP=1
  elif [[ "$USE_1PASSWORD" == "auto" ]] && grep -Eq '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=.*op://' "$DOTENV_PATH"; then
    NEEDS_OP=1
  fi
fi

if [[ "$NEEDS_OP" == "1" ]]; then
  OP_BIN="$(resolve_op_binary || true)"
  if [[ -z "${OP_BIN:-}" ]]; then
    echo "secure_exec: 1Password CLI (op) is required but not installed."
    exit 1
  fi
  exec "$OP_BIN" run --env-file "$DOTENV_PATH" -- "$@"
fi

meetingctl_load_env "$ROOT_DIR"
exec "$@"
