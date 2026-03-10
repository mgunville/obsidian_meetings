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
    export MEETINGCTL_ENV_PROFILE="${MEETINGCTL_HAZEL_ENV_PROFILE:-secure}"
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

ensure_op_signed_in() {
  local op_bin="$1"
  if "$op_bin" whoami >/dev/null 2>&1; then
    return 0
  fi

  local is_interactive=0
  if [[ -t 0 || -t 1 || -t 2 ]]; then
    is_interactive=1
  fi

  local open_app="${MEETINGCTL_OP_OPEN_APP_ON_AUTH_FAILURE:-}"
  if [[ -z "$open_app" ]]; then
    if [[ "$is_interactive" -eq 1 ]]; then
      open_app=1
    else
      open_app=0
    fi
  fi

  local wait_seconds="${MEETINGCTL_OP_AUTH_WAIT_SECONDS:-}"
  if [[ -z "$wait_seconds" ]]; then
    if [[ "$is_interactive" -eq 1 ]]; then
      wait_seconds=20
    else
      wait_seconds=0
    fi
  fi
  if [[ ! "$wait_seconds" =~ ^[0-9]+$ ]]; then
    wait_seconds=20
  fi

  if [[ "$open_app" != "0" ]] && command -v open >/dev/null 2>&1; then
    open -a "1Password" >/dev/null 2>&1 || true
  fi

  echo "secure_exec: 1Password CLI is not signed in." >&2
  if [[ "$is_interactive" -eq 1 ]]; then
    echo "secure_exec: unlock/sign in to the 1Password app. Waiting up to ${wait_seconds}s for authentication..." >&2
  else
    echo "secure_exec: background run will not open 1Password or steal focus. Use cached env values, direct env vars, or local token files for headless runs." >&2
  fi

  if [[ "$is_interactive" -eq 1 ]]; then
    local remaining="$wait_seconds"
    while [[ "$remaining" -gt 0 ]]; do
      if "$op_bin" whoami >/dev/null 2>&1; then
        echo "secure_exec: 1Password authentication detected." >&2
        return 0
      fi
      sleep 1
      remaining=$((remaining - 1))
    done
  fi

  echo "secure_exec: timed out waiting for 1Password auth. Verify with: op whoami" >&2
  return 1
}

dotenv_get_value() {
  local dotenv_path="$1"
  local wanted_key="$2"
  awk -F= -v key="$wanted_key" '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    {
      line=$0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      split(line, parts, "=")
      k=parts[1]
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
      if (k == key) {
        value=substr(line, index(line, "=") + 1)
        gsub(/^["'"'"']|["'"'"']$/, "", value)
        print value
        exit
      }
    }
  ' "$dotenv_path"
}

dotenv_keys() {
  local dotenv_path="$1"
  awk -F= '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    {
      line=$0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      key=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
      if (key ~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
        print key
      }
    }
  ' "$dotenv_path"
}

is_concealed_value() {
  local value="${1:-}"
  [[ "$value" == "<concealed by 1Password>"* ]]
}

sha256_file() {
  local path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | awk '{print $1}'
    return 0
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
    return 0
  fi
  stat -f "%m" "$path"
}

load_cached_op_env_and_exec() {
  local op_bin="$1"
  local dotenv_path="$2"
  shift 2

  local ttl="${MEETINGCTL_OP_CACHE_TTL_SECONDS:-}"
  if [[ -z "$ttl" && -f "$dotenv_path" ]]; then
    ttl="$(dotenv_get_value "$dotenv_path" "MEETINGCTL_OP_CACHE_TTL_SECONDS" || true)"
  fi
  ttl="${ttl:-0}"
  if ! [[ "$ttl" =~ ^[0-9]+$ ]]; then
    ttl=0
  fi

  if [[ "$ttl" -le 0 ]]; then
    exec "$op_bin" run --env-file "$dotenv_path" -- "$@"
  fi

  local cache_dir="${MEETINGCTL_OP_CACHE_DIR:-}"
  if [[ -z "$cache_dir" && -f "$dotenv_path" ]]; then
    cache_dir="$(dotenv_get_value "$dotenv_path" "MEETINGCTL_OP_CACHE_DIR" || true)"
  fi
  cache_dir="${cache_dir:-$HOME/.cache/meetingctl/op}"
  if [[ "$cache_dir" == "~/"* ]]; then
    cache_dir="$HOME/${cache_dir#"~/"}"
  fi
  mkdir -p "$cache_dir"
  chmod 700 "$cache_dir" 2>/dev/null || true

  local dotenv_hash
  dotenv_hash="$(sha256_file "$dotenv_path")"
  local cache_env_file="$cache_dir/resolved-${dotenv_hash}.env"
  local cache_meta_file="$cache_dir/resolved-${dotenv_hash}.meta"
  local now_epoch
  now_epoch="$(date +%s)"

  local expires_epoch=0
  if [[ -f "$cache_meta_file" ]]; then
    expires_epoch="$(awk -F= '/^expires_epoch=/{print $2; exit}' "$cache_meta_file" 2>/dev/null || true)"
    if ! [[ "${expires_epoch:-}" =~ ^[0-9]+$ ]]; then
      expires_epoch=0
    fi
  fi

  if [[ -f "$cache_env_file" && "$expires_epoch" -gt "$now_epoch" ]]; then
    load_dotenv_file "$cache_env_file"
    exec "$@"
  fi

  local env_dump
  env_dump="$("$op_bin" run --env-file "$dotenv_path" -- env)"

  local tmp_env
  local tmp_meta
  tmp_env="$(mktemp "$cache_dir/resolved-env.XXXXXX")"
  tmp_meta="$(mktemp "$cache_dir/resolved-meta.XXXXXX")"
  chmod 600 "$tmp_env" "$tmp_meta" 2>/dev/null || true

  local key line value raw_value
  while IFS= read -r key; do
    [[ -z "$key" ]] && continue
    value=""
    raw_value="$(dotenv_get_value "$dotenv_path" "$key" || true)"
    if [[ "$raw_value" == op://* ]]; then
      value="$("$op_bin" read "$raw_value" 2>/dev/null || true)"
      # Some `op run -- env` surfaces redacted placeholders; prefer explicit `op read`.
      if is_concealed_value "$value"; then
        value=""
      fi
    fi
    if [[ -z "$value" ]]; then
      line="$(printf '%s\n' "$env_dump" | rg -m1 "^${key}=" || true)"
      if [[ -n "$line" ]]; then
        value="${line#*=}"
      fi
    fi
    if is_concealed_value "$value" && [[ "$raw_value" == op://* ]]; then
      value="$("$op_bin" read "$raw_value" 2>/dev/null || true)"
    fi
    printf '%s=%s\n' "$key" "$value" >> "$tmp_env"
  done < <(dotenv_keys "$dotenv_path")

  printf 'expires_epoch=%s\n' "$((now_epoch + ttl))" > "$tmp_meta"
  printf 'dotenv_path=%s\n' "$dotenv_path" >> "$tmp_meta"

  mv "$tmp_env" "$cache_env_file"
  mv "$tmp_meta" "$cache_meta_file"

  load_dotenv_file "$cache_env_file"
  exec "$@"
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
  ensure_op_signed_in "$OP_BIN"
  load_cached_op_env_and_exec "$OP_BIN" "$DOTENV_PATH" "$@"
fi

meetingctl_load_env "$ROOT_DIR"
exec "$@"
