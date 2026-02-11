#!/usr/bin/env bash
set -euo pipefail

# Bootstraps a local WhisperX-compatible Faster-Whisper model for this repo.
# Strategy:
# 1) Reuse an existing local model dir if present (preferred).
# 2) Otherwise optionally download model artifacts with curl.
# 3) Create/update project symlink at config/models/whisperx/faster-whisper-base.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_ROOT="$ROOT_DIR/config/models/whisperx"
TARGET_LINK="$MODEL_ROOT/faster-whisper-base"
MODEL_REPO="Systran/faster-whisper-base"
LINK_ONLY=0

if [[ "${1:-}" == "--link-only" ]]; then
  LINK_ONLY=1
fi

mkdir -p "$MODEL_ROOT"

is_valid_model_dir() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  [[ -f "$dir/model.bin" ]] || return 1
  [[ -f "$dir/config.json" ]] || return 1
  [[ -f "$dir/tokenizer.json" ]] || return 1
  return 0
}

link_model_dir() {
  local source_dir="$1"
  local resolved
  resolved="$(cd "$source_dir" && pwd)"
  if [[ -L "$TARGET_LINK" || -e "$TARGET_LINK" ]]; then
    rm -rf "$TARGET_LINK"
  fi
  ln -s "$resolved" "$TARGET_LINK"
  echo "Linked model: $TARGET_LINK -> $resolved"
}

find_existing_model_dir() {
  local candidates=(
    "$ROOT_DIR/config/models/whisperx/faster-whisper-base.local"
    "$HOME/Documents/Dev/audio-transcriber/models/faster-whisper-base"
    "$HOME/Notes/audio/transcriber/models/faster-whisper-base"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if is_valid_model_dir "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done

  local hf_root="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-base/snapshots"
  if [[ -d "$hf_root" ]]; then
    local snapshot
    for snapshot in "$hf_root"/*; do
      if is_valid_model_dir "$snapshot"; then
        echo "$snapshot"
        return 0
      fi
    done
  fi

  # Best-effort deeper search in common roots for an existing faster-whisper-base checkout/cache.
  local search_roots=(
    "$HOME/Documents"
    "$HOME/Notes"
  )
  local root
  for root in "${search_roots[@]}"; do
    [[ -d "$root" ]] || continue
    while IFS= read -r model_bin; do
      local dir
      dir="$(dirname "$model_bin")"
      if is_valid_model_dir "$dir"; then
        echo "$dir"
        return 0
      fi
    done < <(find "$root" -maxdepth 6 -type f -name "model.bin" 2>/dev/null | grep "faster-whisper-base" || true)
  done
  return 1
}

download_with_curl() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl not found; cannot download model." >&2
    return 1
  fi
  local out_dir="$MODEL_ROOT/faster-whisper-base.local"
  mkdir -p "$out_dir"

  local base_url="https://huggingface.co/${MODEL_REPO}/resolve/main"
  local required_files=(
    "config.json"
    "tokenizer.json"
    "model.bin"
  )
  local optional_files=(
    "vocabulary.txt"
    "vocabulary.json"
    "preprocessor_config.json"
  )

  echo "Downloading required WhisperX model files via curl..." >&2
  local file
  for file in "${required_files[@]}"; do
    curl -fL "${base_url}/${file}?download=1" -o "${out_dir}/${file}"
  done

  for file in "${optional_files[@]}"; do
    curl -fsL "${base_url}/${file}?download=1" -o "${out_dir}/${file}" || true
  done

  if ! is_valid_model_dir "$out_dir"; then
    echo "Downloaded files are incomplete at ${out_dir}" >&2
    return 1
  fi
  echo "$out_dir"
}

if existing="$(find_existing_model_dir)"; then
  link_model_dir "$existing"
  exit 0
fi

if [[ "$LINK_ONLY" -eq 1 ]]; then
  echo "No existing local model found. Run scripts/bootstrap_whisperx_model.sh to download with curl."
  exit 1
fi

downloaded="$(download_with_curl)"
link_model_dir "$downloaded"
echo "WhisperX model bootstrap complete."
