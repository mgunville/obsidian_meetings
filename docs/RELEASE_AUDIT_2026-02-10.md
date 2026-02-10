# Release Audit (2026-02-10)

## Scope
- Verify latest runtime/component status after config and docs consolidation.
- Reconfirm key contracts and test stability after platform-policy updates.

## Validation Summary
- Test suite:
  - `pytest -q` passes.
- Doctor:
  - `meetingctl doctor --json` reports `ok: true`.
  - Calendar permissions report authorized (full access).
- Event resolution:
  - `meetingctl event --now-or-next 1440 --json` returns no event in current window.
  - This indicates scheduling/window conditions, not permission failure.
- Keyboard Maestro:
  - Macro bundle imported from `config/km/Meeting-Automation-Macros.kmmacros`.
  - CLI trigger check succeeds asynchronously via KM Engine.
- Backfill calendar matching dry-run:
  - command runs successfully (`failed_jobs: 0`).
  - current recordings in test set remain unmatched (`matched_calendar: 0`, `unmatched_calendar: 4`).

## Behavioral Changes Confirmed
- Config consolidation:
  - KM bundle is now under `config/km/`.
  - Audio Hijack session exports are under `config/audio_hijack_sessions/`.
- Platform policy:
  - `system` platform is disabled by default.
  - unknown platform fallback now uses `meet` (`Browser+Mic`).
  - `system` can be explicitly enabled with `MEETINGCTL_ENABLE_SYSTEM_PLATFORM=1`.
- Audio Hijack mitigation:
  - Optional script-driven control supported through:
    - `MEETINGCTL_AUDIO_HIJACK_START_SCRIPT`
    - `MEETINGCTL_AUDIO_HIJACK_STOP_SCRIPT`

## Remaining Operational Dependencies
- To close Audio Hijack control fully:
  - provide working AH start/stop script files and set the above env vars.
- To close event-resolution smoke fully:
  - rerun `meetingctl event` during an active/near-future event window.
