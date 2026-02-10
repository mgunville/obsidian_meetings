# Outstanding Tasks (Canonical)

Last updated: 2026-02-10 (late)

This is the single source of truth for active work. Other planning/audit docs are historical snapshots.

## Resolved in code/tests

- [x] Ad-hoc start path guarantees `note_path` (explicit `--note-path` or auto-created ad-hoc note).
- [x] Queue processing uses strict WAV resolution (`wav_path` payload first, else `<meeting_id>.wav`).
- [x] Installer uses `python3` with explicit `>=3.11` version check.
- [x] Anthropic summary response parsing handles empty/non-text content blocks with deterministic errors.
- [x] Setup docs include queue WAV behavior.

## Active outstanding tasks

- [ ] Calendar permission and event resolution closure:
  - Calendar permission is now granted in the real runtime.
  - `meetingctl doctor --json` now reports `calendar_permissions: authorized (full access)`.
  - `meetingctl event --now-or-next 1440 --json` currently returns no ongoing/upcoming event in window (environment/timing, not permission).
- [ ] Keyboard Maestro macro activation/import closure:
  - Keyboard Maestro CLI exists (`keyboardmaestro 11.0.4`).
  - Triggering `E6S3-STATUS` currently returns:
    - `Found no macros with a matching name (macros must be enabled, and in macro groups that are enabled and currently active)`.
  - Recovery incident (2026-02-09):
    - direct plist injection approach caused Keyboard Maestro Editor crash on launch.
    - restored safely from local backup: `Keyboard Maestro Macros.backup-20260209-223019.plist`.
    - policy: do not modify Keyboard Maestro plist directly; use only UI import of KM-exported valid bundles.
  - Required: ensure `/config/km/Meeting-Automation-Macros.kmmacros` is imported/enabled in active macro group, then re-run macro trigger checks.
- [ ] Audio Hijack session-control API alignment:
  - App is installed and scriptable at basic level (`tell application "Audio Hijack" to get name` works).
  - Current JXA session call shape (`sessionWithName(...).start()/stop()`) returns `Message not understood (-1708)`.
  - Reproduced through project path:
    - `meetingctl start --title ... --platform system ...` fails at recorder call with non-zero `osascript` status (when system mode is enabled).
  - Mitigation now available:
    - `meetingctl` supports script-driven control via:
      - `MEETINGCTL_AUDIO_HIJACK_START_SCRIPT`
      - `MEETINGCTL_AUDIO_HIJACK_STOP_SCRIPT`
    - these are executed with `open -a "Audio Hijack" ...` before direct `osascript` fallback.
  - `system` platform is now disabled by default and must be explicitly enabled:
    - `MEETINGCTL_ENABLE_SYSTEM_PLATFORM=1`
  - Remaining: provide/validate working `.ahscript` files for local session start/stop.
- [x] Recordings folder read/write capability verified:
  - Read: `RECORDINGS_PATH` exists and files are visible.
  - Write: create/delete probe succeeded (`WRITE_OK=1`).
- [x] Calendar-assisted rename feasibility check executed:
  - `meetingctl backfill --match-calendar --rename --dry-run` ran successfully over discovered recordings.
  - Current result: `matched_calendar=0` / `unmatched_calendar=4` (no event matches for tested recordings in available calendar data).
- [ ] Update release/integration audit docs with fresh real-machine results from this run.

## Deferred by request

- [ ] End-to-end orchestration run (after individual component checks pass).
