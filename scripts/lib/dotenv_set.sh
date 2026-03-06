#!/usr/bin/env bash

dotenv_set_key() {
  local dotenv_path="$1"
  local key="$2"
  local value="$3"

  mkdir -p "$(dirname "$dotenv_path")"
  if [[ ! -f "$dotenv_path" ]]; then
    printf '%s=%s\n' "$key" "$value" >"$dotenv_path"
    return 0
  fi

  local tmp_file
  tmp_file="$(mktemp "${dotenv_path}.tmp.XXXXXX")"
  awk -v wanted_key="$key" -v wanted_value="$value" '
    BEGIN { replaced = 0 }
    {
      line = $0
      normalized = line
      sub(/^[[:space:]]*export[[:space:]]+/, "", normalized)
      split(normalized, parts, "=")
      candidate_key = parts[1]
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", candidate_key)
      if (candidate_key == wanted_key) {
        print wanted_key "=" wanted_value
        replaced = 1
        next
      }
      print line
    }
    END {
      if (!replaced) {
        print wanted_key "=" wanted_value
      }
    }
  ' "$dotenv_path" >"$tmp_file"

  chmod --reference="$dotenv_path" "$tmp_file" 2>/dev/null || true
  mv "$tmp_file" "$dotenv_path"
}
