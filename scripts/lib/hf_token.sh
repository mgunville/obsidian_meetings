#!/usr/bin/env bash

meetingctl_load_hf_token_from_file() {
  local existing
  for existing in "${PYANNOTE_AUTH_TOKEN:-}" "${HF_TOKEN:-}" "${HUGGINGFACE_TOKEN:-}"; do
    [[ -z "$existing" ]] && continue
    if [[ "$existing" != op://* && "$existing" != "<concealed by 1Password>"* ]]; then
      return 0
    fi
  done

  local key raw_path token_path token
  for key in MEETINGCTL_HF_TOKEN_FILE HUGGINGFACE_TOKEN_FILE HF_TOKEN_FILE PYANNOTE_AUTH_TOKEN_FILE; do
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
      export HUGGINGFACE_TOKEN="$token"
      return 0
    fi
  done

  token_path="$HOME/.config/meetingctl/hf_token"
  if [[ -f "$token_path" ]]; then
    token="$(tr -d '\r' < "$token_path" | awk 'NF{print; exit}')"
    token="${token#"${token%%[![:space:]]*}"}"
    token="${token%"${token##*[![:space:]]}"}"
    if [[ -n "$token" ]]; then
      export HUGGINGFACE_TOKEN="$token"
      return 0
    fi
  fi
  return 0
}
