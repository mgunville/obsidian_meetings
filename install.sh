#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"

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

DEFAULT_DOTENV_PATH="$(meetingctl_default_dotenv_path)"
if [ ! -f "$DEFAULT_DOTENV_PATH" ] && [ -f .env.example ]; then
  mkdir -p "$(dirname "$DEFAULT_DOTENV_PATH")"
  cp .env.example "$DEFAULT_DOTENV_PATH"
  chmod 600 "$DEFAULT_DOTENV_PATH" || true
  echo "Created env file from .env.example at: $DEFAULT_DOTENV_PATH"
fi

chmod +x scripts/eventkit_fetch.py

echo ""
echo "Install complete."
echo "1) Edit env file paths if needed (default: $(meetingctl_default_dotenv_path))."
echo "2) Run doctor:"
echo "   source scripts/lib/load_dotenv.sh && meetingctl_load_env \"$ROOT_DIR\" && PYTHONPATH=src .venv/bin/python -m meetingctl.cli doctor --json"
echo "3) Run tests:"
echo "   .venv/bin/python -m pytest"
echo "4) Run one-file transcription smoke check:"
echo "   .venv/bin/python -m whisper --help | head -n 5"

# Optional security hook setup
if command -v pre-commit >/dev/null 2>&1; then
  if [ -d .git ]; then
    pre-commit install --install-hooks || true
    echo "pre-commit hooks installed (including gitleaks)."
  fi
else
  echo "Optional: install pre-commit to enable gitleaks hooks."
fi
