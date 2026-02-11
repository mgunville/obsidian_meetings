#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Missing .venv. Run install/setup first."
  exit 1
fi

source .venv/bin/activate

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PYTHONPATH=src

# Single-pass ingest + queue processing for file-triggered automation (Hazel/KM).
python -m meetingctl.cli ingest-watch --once --match-calendar --json
python -m meetingctl.cli process-queue --json
