#!/usr/bin/env bash
set -euo pipefail

pick_python_bin() {
  local candidate
  candidate="$(which -a python3.11 2>/dev/null | grep -v '/.pyenv/shims/' | head -n 1 || true)"
  if [ -n "$candidate" ]; then
    echo "$candidate"
    return 0
  fi
  candidate="$(which -a python3 2>/dev/null | grep -v '/.pyenv/shims/' | head -n 1 || true)"
  if [ -n "$candidate" ]; then
    echo "$candidate"
    return 0
  fi
  return 1
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="$(pick_python_bin || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "A non-pyenv-shim python3.11 (preferred) or python3 (3.11+) is required."
  exit 1
fi

PYTHON_OK="$("$PYTHON_BIN" -c 'import sys; print("1" if sys.version_info >= (3, 11) else "0")')"
if [ "$PYTHON_OK" != "1" ]; then
  echo "Selected python version must be 3.11 or newer."
  "$PYTHON_BIN" -V
  exit 1
fi

"$PYTHON_BIN" -m venv .venv
VENV_PY="$ROOT_DIR/.venv/bin/python"
VENV_PIP="$ROOT_DIR/.venv/bin/pip"
"$VENV_PY" -m pip install --upgrade pip setuptools wheel
if [ -f requirements.txt ]; then
  "$VENV_PIP" install -r requirements.txt
else
  "$VENV_PIP" install -e ".[dev]"
fi
"$VENV_PIP" install openai-whisper

"$VENV_PY" - <<'PY'
import importlib
missing = [m for m in ("setuptools", "wheel") if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit(f"Missing packaging modules in .venv: {', '.join(missing)}")
print("Packaging backend check: OK")
PY

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

chmod +x scripts/eventkit_fetch.py
chmod +x scripts/bootstrap_whisperx_model.sh

if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg check: OK"
else
  echo "ffmpeg check: missing (install with: brew install ffmpeg)"
fi

if [ -x scripts/eventkit_fetch.py ]; then
  echo "EventKit helper check: OK (scripts/eventkit_fetch.py executable)"
else
  echo "EventKit helper check: FAILED (scripts/eventkit_fetch.py not executable)"
fi

if scripts/bootstrap_whisperx_model.sh --link-only >/dev/null 2>&1; then
  echo "WhisperX model link check: OK"
else
  echo "WhisperX model link check: not linked (run scripts/bootstrap_whisperx_model.sh to download/link)"
fi

if [ -f .env ]; then
  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
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
PYTHONPATH=src "$VENV_PY" -m meetingctl.cli doctor --json || true
if ! "$VENV_PY" -m whisper --help >/dev/null 2>&1; then
  echo "Whisper CLI check: FAILED (run .venv/bin/pip install openai-whisper)"
else
  echo "Whisper CLI check: OK"
fi

echo "Setup complete. Activate with: source .venv/bin/activate"
