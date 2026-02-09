#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "python3.11 is required. Install Python 3.11+ first."
  exit 1
fi

cd "$ROOT_DIR"

python3.11 -m venv .venv
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
