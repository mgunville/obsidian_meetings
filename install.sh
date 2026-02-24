#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

PYTHON_BIN="$(pick_python_bin || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "A non-pyenv-shim python3.11 (preferred) or python3 (3.11+) is required."
  exit 1
fi

cd "$ROOT_DIR"

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
"$VENV_PIP" install -r requirements.txt
"$VENV_PIP" install openai-whisper

"$VENV_PY" - <<'PY'
import importlib
missing = [m for m in ("setuptools", "wheel") if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit(f"Missing packaging modules in .venv: {', '.join(missing)}")
print("Packaging backend check: OK")
PY

if ! "$VENV_PY" -m whisper --help >/dev/null 2>&1; then
  echo "WARNING: whisper CLI/module is unavailable in .venv."
  echo "Run: .venv/bin/pip install openai-whisper"
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

chmod +x scripts/eventkit_fetch.py

echo ""
echo "Install complete."
echo "1) Edit .env paths if needed."
echo "2) Run doctor:"
echo "   set -a && source .env && set +a && PYTHONPATH=src .venv/bin/python -m meetingctl.cli doctor --json"
echo "3) Run tests:"
echo "   .venv/bin/python -m pytest"
echo "4) Run one-file transcription smoke check:"
echo "   .venv/bin/python -m whisper --help | head -n 5"
