#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"

PROFILE="${MEETINGCTL_ENV_PROFILE:-secure}"
EXTENSIONS="wav,m4a"
RUN_PULL=1
RUN_DOCTOR=1
RUN_BACKFILL=1
RUN_DIARIZATION=0
DRY_RUN=0

log() {
  echo "[setup-upgrade] $*"
}

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

append_if_missing() {
  local env_path="$1"
  local key="$2"
  local value="$3"
  if rg -q "^${key}=" "$env_path" 2>/dev/null; then
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "would append ${key} to ${env_path}"
    return 0
  fi
  printf '%s=%s\n' "$key" "$value" >> "$env_path"
}

usage() {
  cat <<'USAGE'
Usage: scripts/setup_upgrade_and_backfill.sh [options]

Rebuild the local runtime as a clean install, ensure the secure env exists,
run doctor, and process all recordings in RECORDINGS_PATH via backfill.

Options:
  --profile <name>         Env profile to use (default: secure)
  --extensions <list>      Backfill extensions (default: wav,m4a)
  --skip-pull              Do not fetch/pull from git
  --skip-doctor            Do not run doctor after install
  --skip-backfill          Do not run calendar-matched process-now backfill
  --with-diarization       Run diarization catch-up after backfill
  --dry-run                Print actions without changing anything
  --help                   Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --extensions)
      EXTENSIONS="$2"
      shift 2
      ;;
    --skip-pull)
      RUN_PULL=0
      shift
      ;;
    --skip-doctor)
      RUN_DOCTOR=0
      shift
      ;;
    --skip-backfill)
      RUN_BACKFILL=0
      shift
      ;;
    --with-diarization)
      RUN_DIARIZATION=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 2
      ;;
  esac
done

cd "$ROOT_DIR"
export MEETINGCTL_ENV_PROFILE="$PROFILE"

git_pull_if_clean() {
  if [[ ! -d .git ]]; then
    log "skipping git pull: no .git directory"
    return 0
  fi
  if ! git remote get-url origin >/dev/null 2>&1; then
    log "skipping git pull: no origin remote"
    return 0
  fi
  if [[ -n "$(git status --porcelain)" ]]; then
    log "skipping git pull: worktree is not clean"
    return 0
  fi

  local branch
  branch="$(git branch --show-current)"
  if [[ -z "$branch" ]]; then
    log "skipping git pull: unable to determine current branch"
    return 0
  fi

  log "fetching latest ${branch} from origin"
  run_cmd git fetch origin "$branch"
  run_cmd git pull --ff-only origin "$branch"
}

ensure_env_profile() {
  local env_path
  env_path="$(meetingctl_default_dotenv_path)"
  local env_dir
  env_dir="$(dirname "$env_path")"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "would ensure env file exists at ${env_path}"
  else
    mkdir -p "$env_dir"
    chmod 700 "$env_dir" 2>/dev/null || true
    if [[ ! -f "$env_path" ]]; then
      cat > "$env_path" <<EOF
VAULT_PATH=~/Notes/notes-vault
RECORDINGS_PATH=~/Notes/audio
MEETINGCTL_ENV_PROFILE=${PROFILE}
MEETINGCTL_ARTIFACTS_ROOT=Meetings/_artifacts
MEETINGCTL_MATCH_WINDOW_MINUTES=30
MEETINGCTL_INGEST_FORWARD_WINDOW_MINUTES=10
MEETINGCTL_INGEST_BACKWARD_WINDOW_MINUTES=15
MEETINGCTL_INGEST_MIN_AGE_SECONDS=15
MEETINGCTL_USE_1PASSWORD=auto
MEETINGCTL_OP_CACHE_TTL_SECONDS=36000
MEETINGCTL_OP_CACHE_DIR=~/.local/state/meetingctl/op-cache
EOF
      chmod 600 "$env_path" 2>/dev/null || true
    fi
  fi

  append_if_missing "$env_path" "VAULT_PATH" "~/Notes/notes-vault"
  append_if_missing "$env_path" "RECORDINGS_PATH" "~/Notes/audio"
  append_if_missing "$env_path" "MEETINGCTL_ENV_PROFILE" "$PROFILE"
  append_if_missing "$env_path" "MEETINGCTL_ARTIFACTS_ROOT" "Meetings/_artifacts"
  append_if_missing "$env_path" "MEETINGCTL_MATCH_WINDOW_MINUTES" "30"
  append_if_missing "$env_path" "MEETINGCTL_INGEST_FORWARD_WINDOW_MINUTES" "10"
  append_if_missing "$env_path" "MEETINGCTL_INGEST_BACKWARD_WINDOW_MINUTES" "15"
  append_if_missing "$env_path" "MEETINGCTL_INGEST_MIN_AGE_SECONDS" "15"
  append_if_missing "$env_path" "MEETINGCTL_USE_1PASSWORD" "auto"
  append_if_missing "$env_path" "MEETINGCTL_OP_CACHE_TTL_SECONDS" "36000"
  append_if_missing "$env_path" "MEETINGCTL_OP_CACHE_DIR" "~/.local/state/meetingctl/op-cache"

  if [[ -f "$HOME/.config/meetingctl/hf_token" ]]; then
    append_if_missing "$env_path" "MEETINGCTL_HF_TOKEN_FILE" "~/.config/meetingctl/hf_token"
  fi

  log "using env file ${env_path}"
}

clean_runtime() {
  log "removing runtime artifacts for a clean rebuild"
  run_cmd rm -rf .venv .pytest_cache .ruff_cache build
}

run_install() {
  log "running install.sh"
  run_cmd bash install.sh
}

run_doctor() {
  log "running doctor"
  run_cmd bash scripts/meetingctl_cli.sh doctor --json
}

run_backfill() {
  log "running calendar-matched process-now backfill for ${EXTENSIONS}"
  run_cmd bash scripts/meetingctl_cli.sh backfill \
    --extensions "$EXTENSIONS" \
    --match-calendar \
    --process-now \
    --json
}

run_diarization() {
  log "running diarization catch-up"
  run_cmd bash scripts/run_diarization_backfill.sh
}

if [[ "$RUN_PULL" -eq 1 ]]; then
  git_pull_if_clean
fi

ensure_env_profile
clean_runtime
run_install

if [[ "$RUN_DOCTOR" -eq 1 ]]; then
  run_doctor
fi

if [[ "$RUN_BACKFILL" -eq 1 ]]; then
  run_backfill
fi

if [[ "$RUN_DIARIZATION" -eq 1 ]]; then
  run_diarization
fi

log "complete"
