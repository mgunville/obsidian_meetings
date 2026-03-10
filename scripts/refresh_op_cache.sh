#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"

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

export MEETINGCTL_ENV_PROFILE="${MEETINGCTL_ENV_PROFILE:-secure}"
DOTENV_PATH="$(meetingctl_resolve_dotenv_path "$ROOT_DIR")"
if [[ ! -f "$DOTENV_PATH" ]]; then
  echo "refresh_op_cache: env file not found: $DOTENV_PATH"
  exit 1
fi

OP_BIN="$(resolve_op_binary || true)"
if [[ -z "${OP_BIN:-}" ]]; then
  echo "refresh_op_cache: 1Password CLI (op) is required but not installed."
  exit 1
fi

if ! "$OP_BIN" whoami >/dev/null 2>&1; then
  echo "refresh_op_cache: 1Password CLI is not signed in. Run 'op signin' in this terminal first."
  exit 1
fi

ttl="$(dotenv_get_value "$DOTENV_PATH" "MEETINGCTL_OP_CACHE_TTL_SECONDS" || true)"
ttl="${ttl:-36000}"
if ! [[ "$ttl" =~ ^[0-9]+$ ]]; then
  ttl=36000
fi

cache_dir="$(dotenv_get_value "$DOTENV_PATH" "MEETINGCTL_OP_CACHE_DIR" || true)"
cache_dir="${cache_dir:-$HOME/.local/state/meetingctl/op-cache}"
if [[ "$cache_dir" == "~/"* ]]; then
  cache_dir="$HOME/${cache_dir#"~/"}"
fi
mkdir -p "$cache_dir"
chmod 700 "$cache_dir" 2>/dev/null || true

dotenv_hash="$(sha256_file "$DOTENV_PATH")"
cache_env_file="$cache_dir/resolved-${dotenv_hash}.env"
cache_meta_file="$cache_dir/resolved-${dotenv_hash}.meta"
now_epoch="$(date +%s)"

env_dump="$("$OP_BIN" run --env-file "$DOTENV_PATH" -- env)"

tmp_env="$(mktemp "$cache_dir/resolved-env.XXXXXX")"
tmp_meta="$(mktemp "$cache_dir/resolved-meta.XXXXXX")"
chmod 600 "$tmp_env" "$tmp_meta" 2>/dev/null || true

while IFS= read -r key; do
  [[ -z "$key" ]] && continue
  value=""
  raw_value="$(dotenv_get_value "$DOTENV_PATH" "$key" || true)"
  if [[ "$raw_value" == op://* ]]; then
    value="$("$OP_BIN" read "$raw_value" 2>/dev/null || true)"
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
    value="$("$OP_BIN" read "$raw_value" 2>/dev/null || true)"
  fi
  printf '%s=%s\n' "$key" "$value" >> "$tmp_env"
done < <(dotenv_keys "$DOTENV_PATH")

printf 'expires_epoch=%s\n' "$((now_epoch + ttl))" > "$tmp_meta"
printf 'dotenv_path=%s\n' "$DOTENV_PATH" >> "$tmp_meta"

mv "$tmp_env" "$cache_env_file"
mv "$tmp_meta" "$cache_meta_file"

echo "refresh_op_cache: refreshed cache for $DOTENV_PATH"
echo "refresh_op_cache: env=$cache_env_file"
echo "refresh_op_cache: meta=$cache_meta_file"
