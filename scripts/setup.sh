#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "python3.11 is required. Install Python 3.11+ first."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade setuptools wheel
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  pip install -e .[dev]
fi

python - <<'PY'
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
PYTHONPATH=src python -m meetingctl.cli doctor --json || true

echo "Setup complete. Activate with: source .venv/bin/activate"
