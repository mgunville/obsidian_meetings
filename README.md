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
   - `set -a; source .env; set +a`
   - `PYTHONPATH=src python -m meetingctl.cli doctor --json`

## Backfill Previous Recordings
- Queue historical recordings:
  - `PYTHONPATH=src python -m meetingctl.cli backfill --extensions wav,m4a --json`
- Process immediately instead of queueing:
  - `PYTHONPATH=src python -m meetingctl.cli backfill --extensions wav --process-now --json`
- Calendar-assisted matching from filename timestamp (`yyyymmdd_hhmm`) or file timestamps:
  - preview only: `PYTHONPATH=src python -m meetingctl.cli backfill --match-calendar --dry-run --json`
  - with safe rename to canonical meeting IDs: `PYTHONPATH=src python -m meetingctl.cli backfill --match-calendar --rename --json`

## Working Agreements
- TDD: write/adjust tests first for each story.
- YAGNI: implement only what a story needs.
- Keep interfaces small and typed.

## Documentation
- `docs/DOCS_INDEX.md` (canonical docs entrypoint)
- `docs/OUTSTANDING_TASKS.md` (single active task list)
- `docs/SETUP_AND_DEPENDENCIES.md`
- `docs/TDD_AND_DOD.md`
