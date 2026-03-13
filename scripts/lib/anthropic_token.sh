#!/usr/bin/env bash

meetingctl_load_anthropic_key_from_file() {
  if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    return 0
  fi

  local key raw_path token_path token
  for key in MEETINGCTL_ANTHROPIC_API_KEY_FILE ANTHROPIC_API_KEY_FILE; do
    raw_path="$(eval "printf '%s' \"\${$key-}\"")"
    [[ -z "$raw_path" ]] && continue
    if [[ "$raw_path" == "~/"* ]]; then
      raw_path="$HOME/${raw_path#"~/"}"
    fi
    token_path="$raw_path"
    [[ -f "$token_path" ]] || continue
    token="$(tr -d '\r' < "$token_path" | awk 'NF{print; exit}')"
    token="${token#"${token%%[![:space:]]*}"}"
    token="${token%"${token##*[![:space:]]}"}"
    if [[ -n "$token" ]]; then
      export ANTHROPIC_API_KEY="$token"
      return 0
    fi
  done

  token_path="$HOME/.config/meetingctl/anthropic_api_key"
  if [[ -f "$token_path" ]]; then
    token="$(tr -d '\r' < "$token_path" | awk 'NF{print; exit}')"
    token="${token#"${token%%[![:space:]]*}"}"
    token="${token%"${token##*[![:space:]]}"}"
    if [[ -n "$token" ]]; then
      export ANTHROPIC_API_KEY="$token"
      return 0
    fi
  fi

  return 0
}
