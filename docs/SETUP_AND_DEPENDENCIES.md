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
- `DEFAULT_MEETINGS_FOLDER=_Work/AHEAD/Meetings`
- `MEETINGCTL_NOTE_TEMPLATE_PATH=~/Notes/notes-vault/System/Templates/icalBuddy/Meeting.md`
- `MEETINGCTL_MATCH_WINDOW_MINUTES=30`
- `MEETINGCTL_INGEST_MIN_AGE_SECONDS=15`
- `MEETINGCTL_BACKFILL_EXTENSIONS=wav`
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
- `System+Mic` (optional; disabled by default in `meetingctl`)

Each session should record to WAV and include the required audio sources.
If direct external JXA control is unsupported on your Audio Hijack build, configure script-based control:
- `MEETINGCTL_AUDIO_HIJACK_START_SCRIPT=/absolute/path/to/start.ahscript`
- `MEETINGCTL_AUDIO_HIJACK_STOP_SCRIPT=/absolute/path/to/stop.ahscript`
- `meetingctl` will execute these via `open -a "Audio Hijack" ...` before falling back to direct `osascript`.
`meetingctl` platform behavior:
- default ad-hoc platform is `meet` (`Browser+Mic`)
- unknown platform fallback targets `Browser+Mic`
- `system` platform is opt-in and requires `MEETINGCTL_ENABLE_SYSTEM_PLATFORM=1`
`process-queue` WAV resolution:
- preferred: explicit `wav_path` from queue payload
- otherwise: `<meeting_id>.wav` in `RECORDINGS_PATH`

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

## 6) Transcription Backend Bootstrap
- Install CLI/runtime dependencies with `bash install.sh`.
- Ensure a transcription backend is available on PATH:
  - `whisper` (default in `meetingctl.transcription.WhisperTranscriptionRunner`), or
  - `whisperx` (optional high-detail mode).
- Bootstrap local WhisperX model storage (avoids runtime Python SSL/HuggingFace download issues):
  - Link existing local model if found:
    - `bash scripts/bootstrap_whisperx_model.sh --link-only`
  - Download model with curl and link into project:
    - `bash scripts/bootstrap_whisperx_model.sh`
  - Project model link path:
    - `config/models/whisperx/faster-whisper-base`
- WhisperX runtime knobs (`.env`):
  - `MEETINGCTL_TRANSCRIPTION_BACKEND=whisperx`
  - `MEETINGCTL_WHISPERX_MODEL_PATH=/absolute/path/to/config/models/whisperx/faster-whisper-base`
  - `MEETINGCTL_WHISPERX_VAD_METHOD=silero` (recommended while pyannote/torch compatibility is unstable)
  - `MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER=1`
- Optional dry-run controls for local pipeline validation:
  - `MEETINGCTL_PROCESSING_TRANSCRIBE_DRY_RUN=1`
  - `MEETINGCTL_PROCESSING_SUMMARY_JSON='{"minutes":"...","decisions":[],"action_items":[]}'`
  - `MEETINGCTL_PROCESSING_CONVERT_DRY_RUN=1`

## 7) Backfill (Prior Recordings)
- Queue all matching recordings in `RECORDINGS_PATH`:
  - `PYTHONPATH=src python -m meetingctl.cli backfill --extensions wav,m4a --json`
- Process them immediately:
  - `PYTHONPATH=src python -m meetingctl.cli backfill --extensions wav --process-now --json`
- Calendar-assisted association (filename `yyyymmdd_hhmm` first, then file timestamps):
  - dry-run plan: `PYTHONPATH=src python -m meetingctl.cli backfill --match-calendar --dry-run --json`
  - apply rename to canonical meeting IDs when matched: `PYTHONPATH=src python -m meetingctl.cli backfill --match-calendar --rename --json`

## 8) Automation Entry Point (Hazel / Keyboard Maestro)
- Use `scripts/run_ingest_once.sh` as the single command target for file-triggered automation.
- It runs one ingest pass (`ingest-watch --once --match-calendar`) followed by queue processing.
- Recommended trigger:
  - New `.wav` in `RECORDINGS_PATH` older than `MEETINGCTL_INGEST_MIN_AGE_SECONDS`.
