#!/usr/bin/env bash

# Load KEY=VALUE pairs from a dotenv file without evaluating shell syntax.
# This avoids parse errors when values contain characters like parentheses.
load_dotenv_file() {
  local dotenv_path="${1:-.env}"
  if [[ ! -f "$dotenv_path" ]]; then
    return 0
  fi

  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip blanks and comments.
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue

    # Strip optional leading "export ".
    line="${line#export }"

    # Require key=value format.
    if [[ "$line" != *"="* ]]; then
      continue
    fi

    key="${line%%=*}"
    value="${line#*=}"

    # Trim surrounding whitespace on key only.
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"

    # Accept standard shell var names.
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi

    # Remove matching surrounding quotes from value.
    if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
      value="${value:1:${#value}-2}"
    fi

    # Expand a leading "~/" for convenience.
    if [[ "$value" == "~/"* ]]; then
      value="$HOME/${value#"~/"}"
    fi

    export "$key=$value"
  done < "$dotenv_path"
}

# Resolve env file location with precedence:
# 1) explicit MEETINGCTL_DOTENV_PATH
# 2) user-local ~/.config/meetingctl/env
# 3) repo-local .env (legacy fallback)
meetingctl_resolve_dotenv_path() {
  local root_dir="${1:-$(pwd)}"
  local explicit="${MEETINGCTL_DOTENV_PATH:-}"
  local profile="${MEETINGCTL_ENV_PROFILE:-}"
  local user_local="$HOME/.config/meetingctl/env"
  local user_local_dev="$HOME/.config/meetingctl/env.dev"
  local user_local_secure="$HOME/.config/meetingctl/env.secure"
  local legacy_local="$root_dir/.env"

  if [[ -n "$explicit" ]]; then
    if [[ "$explicit" == "~/"* ]]; then
      explicit="$HOME/${explicit#"~/"}"
    fi
    echo "$explicit"
    return 0
  fi

  if [[ "$profile" == "dev" ]]; then
    if [[ -f "$user_local_dev" ]]; then
      echo "$user_local_dev"
      return 0
    fi
  fi

  if [[ "$profile" == "secure" ]]; then
    if [[ -f "$user_local_secure" ]]; then
      echo "$user_local_secure"
      return 0
    fi
    if [[ -f "$user_local" ]]; then
      echo "$user_local"
      return 0
    fi
  fi

  if [[ -f "$user_local" ]]; then
    echo "$user_local"
    return 0
  fi

  echo "$legacy_local"
}

meetingctl_default_dotenv_path() {
  local explicit="${MEETINGCTL_DOTENV_PATH:-}"
  local profile="${MEETINGCTL_ENV_PROFILE:-}"
  if [[ -n "$explicit" ]]; then
    if [[ "$explicit" == "~/"* ]]; then
      explicit="$HOME/${explicit#"~/"}"
    fi
    echo "$explicit"
    return 0
  fi
  if [[ "$profile" == "dev" ]]; then
    echo "$HOME/.config/meetingctl/env.dev"
    return 0
  fi
  if [[ "$profile" == "secure" ]]; then
    echo "$HOME/.config/meetingctl/env.secure"
    return 0
  fi
  echo "$HOME/.config/meetingctl/env"
}

meetingctl_load_env() {
  local root_dir="${1:-$(pwd)}"
  local dotenv_path
  dotenv_path="$(meetingctl_resolve_dotenv_path "$root_dir")"
  if [[ -f "$dotenv_path" ]]; then
    load_dotenv_file "$dotenv_path"
  fi
}
