# Integration Smoke Report (2026-02-08)

## Scope
- Backlog item: `B3` real-machine integration smoke pass.
- Script: `scripts/smoke-test.sh`.

## Run 1: Local Incremental Mode
- Command:
  - `./scripts/smoke-test.sh`
- Mode:
  - `MEETINGCTL_RECORDING_DRY_RUN=1` (set by script).
- Result:
  - Passed `15/15` tests.
- Validated:
  - CLI availability
  - start/stop/status contract behavior
  - process queue emission
  - warning/error path checks
  - fallback handling
  - JSON validity

## Run 2: Real-Machine Mode
- Command:
  - `SMOKE_REAL_MACHINE=1 ./scripts/smoke-test.sh`
- Result:
  - Failed at `Test 4` (`start` with real Audio Hijack call).
- Failure signal:
  - `osascript` connection invalid / AppleScript error `(-2741)`.
- Interpretation:
  - Real-machine preconditions not satisfied in this environment
    (Audio Hijack app/session and/or Automation permission path unavailable).

## Outcome
- `B3` is **in progress**:
  - local integration smoke: complete
  - real-machine smoke: blocked by host app/permission state

## Follow-up Run: 2026-02-09 (`run-incremental-workflow.sh`)
- Local mode command:
  - `source .venv/bin/activate && set -a && source .env && set +a && bash scripts/run-incremental-workflow.sh`
- Local mode result:
  - End-to-end pass including queue consumer (`processed_jobs=1, failed_jobs=0`).
  - Verified `.env` paths under `~/Notes` were used for note + recordings.
- Real mode command:
  - `source .venv/bin/activate && set -a && source .env && set +a && MODE=real bash scripts/run-incremental-workflow.sh`
- Real mode result:
  - Stopped at `event` with:
    - `No ongoing/upcoming event in window`
    - doctor still reporting `calendar_permissions` not determined.
- Interpretation:
  - Queue pipeline wiring is validated in local mode.
  - Remaining B3 blocker is real calendar permission/access + a live/nearby event at run time.

## Follow-up Run: 2026-02-09 (post E5-S5 wiring hardening)
- Local mode command:
  - `source .venv/bin/activate && set -a && source .env && set +a && bash scripts/run-incremental-workflow.sh`
- Local mode result:
  - pass with queue processing success (`processed_jobs=1`, `failed_jobs=0`)
  - validates end-to-end queue consumer path with `.env` paths under `~/Notes`
- Real mode command:
  - `source .venv/bin/activate && set -a && source .env && set +a && MODE=real bash scripts/run-incremental-workflow.sh`
- Real mode result:
  - still blocked at `event`:
    - `No ongoing/upcoming event in window`
    - doctor reports `calendar_permissions` not determined
- Updated blocker statement:
  - `B3` cannot be closed until Calendar permission is granted and run is executed during an actual now/next calendar event window.

## Required to close B3
1. Install and open Audio Hijack with required sessions (`Teams+Mic`, `Zoom+Mic`, `Browser+Mic`, `System+Mic`).
2. Grant Automation and Accessibility permissions for shell/KM path controlling Audio Hijack.
3. Re-run:
   - `SMOKE_REAL_MACHINE=1 ./scripts/smoke-test.sh`
4. Capture successful full pass output in a follow-up report.
