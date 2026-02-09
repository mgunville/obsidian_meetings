#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "python3.11 is required. Install Python 3.11+ first."
  exit 1
fi

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

chmod +x scripts/eventkit_fetch.py

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

PYTHONPATH=src python -m meetingctl.cli doctor --json || true

echo "Setup complete. Activate with: source .venv/bin/activate"
