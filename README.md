# Meeting Capture Pipeline

Execution repo for the `obsidian_spec.md` implementation.

## Scope
- Build `meetingctl` with TDD + YAGNI.
- macOS-first automation with Keyboard Maestro and Audio Hijack.
- Local-first notes, transcripts, and audio handling.

## External Requirements
Assume these are installed:
- Keyboard Maestro
- Audio Hijack

Install separately:
- Python 3.11+
- ffmpeg (`brew install ffmpeg`)
- Optional transcription engine binaries/models
  - WhisperX model bootstrap helper: `bash scripts/bootstrap_whisperx_model.sh`

## Quick Start (Developers)
1. Bootstrap environment:
   - `bash install.sh`
2. Activate environment:
   - `source .venv/bin/activate`
3. Run tests:
   - `pytest`
4. Run lint:
   - `ruff check .`
5. Run doctor:
   - `bash scripts/meetingctl_cli.sh doctor --json`

## Secret Management (Recommended)
- Keep secrets out of repo/cloud-synced workspace paths.
- Default secure env path is `~/.config/meetingctl/env` (overridable with `MEETINGCTL_DOTENV_PATH`).
- Profile split (recommended):
  - `~/.config/meetingctl/env.dev` (automation, lower friction)
  - `~/.config/meetingctl/env.secure` (manual, higher assurance)
  - initialize: `bash scripts/setup_env_profiles.sh`
- Prefer 1Password secret refs in env file:
  - `MEETINGCTL_ANTHROPIC_API_KEY_OP_REF=op://Private/Anthropic/api_key`
- For corporate TLS inspection / custom root cert environments:
  - keep `MEETINGCTL_SUMMARY_USE_SYSTEM_TRUST=1` (default) so Anthropic requests use macOS trust roots.
- Run commands via secure wrapper:
  - `bash scripts/meetingctl_cli.sh process-queue --json`

## Backfill Previous Recordings
- Wrapper (recommended):
  - preview: `bash scripts/backfill_historical.sh`
  - apply: `bash scripts/backfill_historical.sh --apply`
- Queue historical recordings:
  - `bash scripts/meetingctl_cli.sh backfill --extensions wav,m4a --json`
- Process immediately instead of queueing:
  - `bash scripts/meetingctl_cli.sh backfill --extensions wav --process-now --json`
- Calendar-assisted matching from filename timestamp (`yyyymmdd_hhmm`) or file timestamps:
  - preview only: `bash scripts/meetingctl_cli.sh backfill --match-calendar --dry-run --json`
  - with safe rename to canonical meeting IDs: `bash scripts/meetingctl_cli.sh backfill --match-calendar --rename --json`

## Automation Command
- For Hazel/Keyboard Maestro file-driven automation, run:
  - `bash scripts/run_ingest_once.sh`
- Calendar-matched ingest will reuse an existing note by local date/start time when available, instead of creating a duplicate meeting note.
- Live ingest calendar matching is anchored to current time (`now`) with directional limits:
  - forward max `10m` (`MEETINGCTL_INGEST_FORWARD_WINDOW_MINUTES`)
  - backward max `15m` (`MEETINGCTL_INGEST_BACKWARD_WINDOW_MINUTES`)

## Local Diarization Sidecar
- Use isolated pyannote/whisperx runtime via Docker Compose:
  - build: `docker compose -f docker-compose.diarization.yml build diarizer`
  - run: `bash scripts/diarize_sidecar.sh ~/Notes/audio/<file>.wav --meeting-id <meeting_id>`
- Historical transcript upgrade (recommended, transcript-json-first):
  - `bash scripts/run_diarization_backfill.sh`
  - optional bounded run: `bash scripts/run_diarization_backfill.sh --max-files 25`
- Full guide:
  - `docs/DIARIZATION_SIDECAR.md`
- Historical catch-up and minutes comparison/apply:
  - `./.venv/bin/python scripts/diarization_catchup.py --json`
  - `bash scripts/secure_exec.sh ./.venv/bin/python scripts/diarization_minutes_refresh.py --max-items 10 --json`
  - `bash scripts/secure_exec.sh ./.venv/bin/python scripts/diarization_minutes_refresh.py --max-items 10 --apply-diarized --json`
  - `docs/DIARIZATION_CATCHUP_AGENT.md`

## Working Agreements
- TDD: write/adjust tests first for each story.
- YAGNI: implement only what a story needs.
- Keep interfaces small and typed.

## Documentation
- `docs/DOCS_INDEX.md` (canonical docs entrypoint)
- `docs/OPERATIONS_RUNBOOK.md` (batch commands + maintenance tasks)
- `docs/OUTSTANDING_TASKS.md` (single active task list)
- `docs/SETUP_AND_DEPENDENCIES.md`
- `docs/HAZEL_SETUP.md`
- `docs/TDD_AND_DOD.md`
