# Smoke + Slicing Execution Requirements

This document defines exactly what is required to close the remaining open items:
- `B3` real-machine smoke completion
- `B5` story-scoped commit slicing execution

## Current State
- Story report status:
  - `unmapped_files = 0`
  - `conflicts = 3`
    - `km/Meeting-Automation-Macros.kmmacros` (`E6-S1..E6-S5`)
    - `tests/test_km_macro_package.py` (`E6-S1..E6-S5`)
    - `tests/test_calendar_resolution.py` (`E2-S2`,`E2-S3`)
- Git working tree is currently all untracked (`??` for top-level dirs/files).

## What I Need From You (Slicing: B5)

1. Baseline decision
- Choose one:
  - A) create one initial baseline commit for current tree, then slice future work story-by-story
  - B) fully slice the current tree now (requires staged partitioning from an untracked tree)

2. Conflict policy for shared files
- `tests/test_calendar_resolution.py`:
  - choose split anchor (recommended):
    - E2-S2 = EventKit adapter tests
    - E2-S3 = JXA fallback tests
- `km/Meeting-Automation-Macros.kmmacros` + `tests/test_km_macro_package.py`:
  - choose one:
    - single combined commit for `E6-S1..E6-S5` (recommended, practical for one macro bundle)
    - attempt macro XML/file-level slicing by story (higher risk)

3. Commit metadata policy
- Confirm commit message format, e.g. `E5-S5: queue consumer real pipeline wiring`.

## What I Need From You (Real Smoke: B3)

1. Calendar access
- Grant terminal/Codex app Calendar permission in macOS privacy settings.

2. Audio Hijack availability
- Install Audio Hijack and ensure required sessions exist:
  - `Teams+Mic`
  - `Zoom+Mic`
  - `Browser+Mic`
  - `System+Mic`

3. Runtime test window
- Have one ongoing or near-future calendar event during the real smoke run window.

## What I Can Execute Immediately (No Additional Input Needed)

1. Re-run local end-to-end verification
- `source .venv/bin/activate && set -a && source .env && set +a && bash scripts/run-incremental-workflow.sh`

2. Rebuild slicing report
- `python3 scripts/story_commit_slicing_report.py --write-json docs/STORY_COMMIT_SLICING_REPORT.json`

3. Full test suite
- `source .venv/bin/activate && pytest -q`

## What I Will Execute As Soon As Inputs Are Provided

1. Real smoke closure (`B3`)
- `source .venv/bin/activate && set -a && source .env && set +a && MODE=real bash scripts/run-incremental-workflow.sh`
- `SMOKE_REAL_MACHINE=1 ./scripts/smoke-test.sh`

2. Commit slicing closure (`B5`)
- Stage files per story based on `docs/STORY_COMMIT_SLICING_REPORT.json`.
- Resolve the 3 conflict files using your selected policy.
- Create one commit per story for all remaining story-scoped changes.
