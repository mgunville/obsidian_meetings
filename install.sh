#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "python3.11 (preferred) or python3 (3.11+) is required."
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
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pip install --upgrade setuptools wheel

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

echo ""
echo "Install complete."
echo "1) Edit .env paths if needed."
echo "2) Run doctor:"
echo "   source .venv/bin/activate && set -a && source .env && set +a && PYTHONPATH=src python -m meetingctl.cli doctor --json"
echo "3) Run tests:"
echo "   source .venv/bin/activate && pytest"
