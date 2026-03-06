# Outstanding Tasks (Canonical)

Last updated: 2026-03-06

This is the single source of truth for active work. Other planning/audit docs are historical snapshots.

## Current session memory (2026-03-06)

- Canonical repo location moved to:
  - `/Users/michael.gunville/Dev/obsidian_meetings`
- Compatibility symlink currently in place:
  - `/Users/michael.gunville/Documents/Dev/obsidian_meetings -> /Users/michael.gunville/Dev/obsidian_meetings`
- Local env profiles rewired to new repo root:
  - `~/.config/meetingctl/env`
  - `~/.config/meetingctl/env.secure`
  - `~/.config/meetingctl/env.dev`
- 1Password resolved env cache was cleared after path migration:
  - `~/.local/state/meetingctl/op-cache/resolved-*.env|.meta`
- Single-file end-to-end validation completed from new root:
  - input: `/Users/michael.gunville/Notes/audio/20260306-0902_Audio.wav`
  - result: `processed_jobs=1`, `failed_jobs=0`
  - meeting id: `m-822f7a7fbc`
  - note updated under `Meetings/` and artifacts written to `Meetings/_artifacts/m-822f7a7fbc/`
  - sidecar path required fallback to baseline whisper, then transcript-json diarization pass completed and produced `*.diarized.*`

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

- [x] Full end-to-end orchestration on a live meeting:
  - trigger via Hazel file event
  - ingest + queue + transcription + summary + note append
  - verify final note content and section ordering against template
- [ ] Generate/importable Hazel rule artifact on another machine:
  - inspect local Hazel DB/rule format on target host
  - produce `.hazelrules` import package for `run_ingest_once.sh`
  - validate import + trigger behavior without manual rule creation
- [ ] Optional: add Hazel failure/quarantine rule for unmatched or failed recordings.
- [ ] Finalize automation path migration and remove compatibility symlink:
  - update Hazel/KM/other launchers to use `REPO_ROOT=/Users/michael.gunville/Dev/obsidian_meetings`
  - verify no active references to old OneDrive repo path remain
  - remove `/Users/michael.gunville/Documents/Dev/obsidian_meetings` symlink once validated
- [x] Resolve Anthropic API TLS trust issue in this runtime:
  - current error: SSL certificate verification failure
  - restore real Claude summary execution in `process-queue`
  - use `truststore`-backed TLS client for Anthropic requests (`MEETINGCTL_SUMMARY_USE_SYSTEM_TRUST=1`)
- [ ] Post-backlog metadata normalization sweep (after meeting notes are moved to final folders):
  - run `normalize-frontmatter` across target scopes
  - ensure all target fields exist and are populated by location/context rules
  - review unresolved blanks (`client`, `engagement`, `topic`, `opportunity_id`, `project_id`, `team`, `related_notes`)
- [x] Hazel pre-create merge behavior (avoid duplicate meeting notes):
  - when Hazel ingests a new recording, search the vault for an existing meeting `.md` with matching local date + meeting start time.
  - if found, attach/merge audio + artifacts into that existing note instead of creating a new meeting note.
  - if multiple candidates match, pick deterministic best match and log tie-break in JSON output.
  - add tests for:
    - exact match
    - nearest-time match within configured tolerance
    - no match (new note still created)
    - moved note paths outside `Meetings/`
