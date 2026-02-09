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

## Working Agreements
- TDD: write/adjust tests first for each story.
- YAGNI: implement only what a story needs.
- Keep interfaces small and typed.

## Planning Docs
- `docs/EPICS_AND_STORIES.md`
- `docs/TEAM_ASSIGNMENT_PLAN.md`
- `docs/SETUP_AND_DEPENDENCIES.md`
- `docs/TDD_AND_DOD.md`
