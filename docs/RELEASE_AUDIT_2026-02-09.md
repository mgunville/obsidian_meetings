# Release Audit (2026-02-09)

## Scope
- Audit production code for unfinished stubs/placeholders.
- Validate CLI and pipeline behavior via automated tests.
- Confirm migration readiness for moving to a new computer.

## Findings
- No functional stubs remain in `src/meetingctl` command flows.
- `pass` usages are only in exception-class declarations or test helper paths, not unimplemented product behavior.
- Queue worker is wired to real pipeline (`transcribe -> summarize -> patch -> convert`).
- WAV fallback implemented for non-`meeting_id` filenames:
  - uses newest `*.wav` when `<meeting_id>.wav` is unavailable.

## Contract Verification
- `meetingctl status --json` contract fields are preserved:
  - `recording`, `meeting_id`, `title`, `platform`, `duration_human`, `note_path`

## Test Verification
- Full test suite passes (`pytest`).
- Integration smoke (local mode) passes with artifact-chain checks.

## New-Machine Readiness
- Added `requirements.txt` for deterministic dependency install.
- Added `install.sh` bootstrap script.
- Setup script now creates `.env` from `.env.example` and loads it for doctor checks.

## Remaining Operational Dependency
- Real-machine verification still depends on host setup:
  - Audio Hijack sessions exist with exact names
  - macOS runtime permissions granted to the runtime invoking `meetingctl`
  - live now-or-next meeting window for real-mode event resolution checks
