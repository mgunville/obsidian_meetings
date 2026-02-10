#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 (3.11+) is required. Install Python 3.11+ first."
  exit 1
fi

cd "$ROOT_DIR"

PYTHON_OK="$(python3 -c 'import sys; print("1" if sys.version_info >= (3, 11) else "0")')"
if [ "$PYTHON_OK" != "1" ]; then
  echo "python3 version must be 3.11 or newer."
  python3 -V
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

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
