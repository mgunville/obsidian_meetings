# Outstanding Tasks (Canonical)

Last updated: 2026-02-12

This is the single source of truth for active work. Other planning/audit docs are historical snapshots.

## Resolved in code/tests

- [x] Ad-hoc start path guarantees `note_path` (explicit `--note-path` or auto-created ad-hoc note).
- [x] Queue processing uses strict WAV resolution (`wav_path` payload first, else `<meeting_id>.wav`).
- [x] Installer uses `python3` with explicit `>=3.11` version check.
- [x] Anthropic summary response parsing handles empty/non-text content blocks with deterministic errors.
- [x] Setup docs include queue WAV behavior.

## Active outstanding tasks

- [x] Calendar permission and event resolution closure:
  - Calendar permission is granted in real runtime.
  - `meetingctl doctor --json` reports `calendar_permissions: authorized`.
  - Event list parity for local-day display/timezone was validated during recent real-machine checks.
- [x] Keyboard Maestro macro activation/import closure:
  - `config/km/Meeting-Automation-Macros.kmmacros` imports successfully.
  - Trigger verification passes:
    - `keyboardmaestro -a -v "Check Recording Status"` returns async success from KM Engine.
  - Recovery incident (2026-02-09) is documented:
    - direct plist injection caused editor crash and was rolled back.
    - policy remains: do not modify Keyboard Maestro plist directly.
- [x] Audio Hijack session-control alignment (interim workflow):
  - Direct JXA session control remains unsupported on this host (`-1708`).
  - Project now uses script-driven control as primary:
    - `MEETINGCTL_AUDIO_HIJACK_START_SCRIPT`
    - `MEETINGCTL_AUDIO_HIJACK_STOP_SCRIPT`
  - `system` platform remains opt-in (`MEETINGCTL_ENABLE_SYSTEM_PLATFORM=1`).
  - Session/script assets are normalized under `config/audio_hijack/`.
- [x] Recordings folder read/write capability verified:
  - Read: `RECORDINGS_PATH` exists and files are visible.
  - Write: create/delete probe succeeded (`WRITE_OK=1`).
- [x] Calendar-assisted rename feasibility check executed:
  - `meetingctl backfill --match-calendar --rename --dry-run` ran successfully over discovered recordings.
  - Current result: `matched_calendar=0` / `unmatched_calendar=4` (no event matches for tested recordings in available calendar data).
- [x] Update release/integration audit docs with fresh real-machine results from this run.
  - Updated snapshot added: `docs/RELEASE_AUDIT_2026-02-10.md`.

## Deferred by request

- [ ] Full end-to-end orchestration on a live meeting:
  - trigger via Hazel file event
  - ingest + queue + transcription + summary + note append
  - verify final note content and section ordering against template
- [ ] Generate/importable Hazel rule artifact on another machine:
  - inspect local Hazel DB/rule format on target host
  - produce `.hazelrules` import package for `run_ingest_once.sh`
  - validate import + trigger behavior without manual rule creation
- [ ] Optional: add Hazel failure/quarantine rule for unmatched or failed recordings.
- [ ] Resolve Anthropic API TLS trust issue in this runtime:
  - current error: SSL certificate verification failure
  - restore real Claude summary execution in `process-queue`
