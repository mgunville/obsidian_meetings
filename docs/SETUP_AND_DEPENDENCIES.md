# Setup and Dependencies

## 1) One-Command Install (new machine)
From repo root:
- `bash install.sh`

This does:
- creates `.venv`
- installs `requirements.txt` (`-e .[dev]`)
- creates `.env` from `.env.example` if missing
- marks `scripts/eventkit_fetch.py` executable

## 2) Required Environment Variables (`.env`)
Minimum required:
- `VAULT_PATH=~/Notes/notes-vault/`
- `RECORDINGS_PATH=~/Notes/recordings`

Optional (already documented in `.env.example`):
- `DEFAULT_MEETINGS_FOLDER=meetings`
- `MEETINGCTL_STATE_FILE=~/.local/state/meetingctl/current.json`
- `MEETINGCTL_PROCESS_QUEUE_FILE=~/.local/state/meetingctl/process_queue.jsonl`
- `MEETINGCTL_PROCESSED_JOBS_FILE=~/.local/state/meetingctl/processed_jobs.jsonl`
- `ANTHROPIC_API_KEY=...`

## 3) Integration Requirements
### Audio Hijack
Create sessions with exact names:
- `Teams+Mic`
- `Zoom+Mic`
- `Browser+Mic`
- `System+Mic`

Each session should record to WAV and include the required audio sources.
`process-queue` now supports WAV discovery fallback:
- preferred: `<meeting_id>.wav`
- fallback: newest `*.wav` in `RECORDINGS_PATH`

### Calendar Backend
Preferred:
- EventKit helper: `scripts/eventkit_fetch.py`

Fallback:
- JXA script: `scripts/calendar_events.jxa`

## 4) macOS Permissions
Grant access for the runtime used to execute `meetingctl`:
- Calendar
- Automation (for app control)
- Microphone/system audio capture

Permission probe:
- `source .venv/bin/activate`
- `python scripts/eventkit_fetch.py --request-access`

## 5) Validation Checklist
1. `source .venv/bin/activate && pytest`
2. `source .venv/bin/activate && set -a && source .env && set +a && PYTHONPATH=src python -m meetingctl.cli doctor --json`
3. Local smoke:
- `bash scripts/smoke-test.sh`
4. Real-mode incremental:
- `MODE=real bash scripts/run-incremental-workflow.sh`
5. Real-machine smoke:
- `SMOKE_REAL_MACHINE=1 bash scripts/smoke-test.sh`
