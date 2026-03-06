# Hazel Setup

Use Hazel as the first-line trigger for completed recordings from two sources:

- local notes audio folder (`~/Notes/audio`)
- Voice Memos sync folder (typically `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings`)

Both rules should run the same script so the ingest/transcription/note-append flow stays identical.

## Rule 1: Notes Audio Folder

- Folder: `~/Notes/audio`
- Rule Name: `MeetingCtl - Ingest Notes Audio`

Conditions:

- `Extension` `is` `wav`
- `or Extension` `is` `m4a`
- `Date Last Modified` `is not in the last` `1` `minute`
- `Name` `does not start with` `.`

## Rule 2: Voice Memos Folder

- Preferred Folder: `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings`
- Rule Name: `MeetingCtl - Ingest Voice Memos`

Conditions:

- `Extension` `is` `m4a`
- `Date Last Modified` `is not in the last` `1` `minute`
- `Name` `does not start with` `.`

If your machine syncs Voice Memos into a different iCloud path, point Rule 2 at that folder instead.

## Hazel Action (Both Rules)

- `Run shell script` with input passed as arguments.

```bash
REPO_ROOT="${MEETINGCTL_REPO:-$HOME/Documents/Dev/obsidian_meetings}"
bash "$REPO_ROOT/scripts/secure_exec.sh" \
  bash "$REPO_ROOT/scripts/hazel_ingest_file.sh" "$1" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
```

## Runtime Behavior

- `hazel_ingest_file.sh` accepts the triggered file path from Hazel.
- It stages files into `RECORDINGS_PATH` (from `.env`) if they originate outside that folder.
- It accepts `.wav` and `.m4a`.
- It then runs `scripts/run_ingest_once.sh`:
  - loads `.env` and `.venv`
  - runs `ingest-watch --once --match-calendar --json`
  - when a calendar match exists, attempts to reuse an existing meeting note anywhere in the vault by matching local date + start time
  - drains `process-queue` in batches so minutes/decisions/action items are generated in the same trigger
    - `MEETINGCTL_PROCESS_QUEUE_MAX_JOBS` (default `3` per pass)
    - `MEETINGCTL_PROCESS_QUEUE_DRAIN_PASSES` (default `6` passes)
  - optional (`MEETINGCTL_NORMALIZE_FRONTMATTER=1`): runs `normalize-frontmatter` for new/moved notes
  - after successful processing, writes an audio completion marker sidecar:
    - `<audio-file>.done.json` (for example `20260302-0900_Audio.wav.done.json`)
- Locking via `~/.local/state/meetingctl/automation_ingest.lock` prevents duplicate concurrent runs.

## Required `.env`

- `RECORDINGS_PATH` should point at your canonical ingest folder (for example `~/Notes/audio`).

## Optional Tuning (`.env`)

- `MEETINGCTL_INGEST_FORWARD_WINDOW_MINUTES=10` (live ingest: max minutes forward from current time)
- `MEETINGCTL_INGEST_BACKWARD_WINDOW_MINUTES=15` (live ingest: max minutes backward from current time)
- `MEETINGCTL_MATCH_WINDOW_MINUTES=30` (backfill/manual matching window around inferred recording timestamp)
- `MEETINGCTL_INGEST_MIN_AGE_SECONDS=15`
- `MEETINGCTL_BACKFILL_EXTENSIONS=wav,m4a`
- `MEETINGCTL_INGEST_EXTENSIONS=wav,m4a`
- `MEETINGCTL_AUTOMATION_STATE_DIR=~/.local/state/meetingctl`
- `MEETINGCTL_VOICEMEMO_FILENAME_TIMEZONE=America/Chicago`
- `MEETINGCTL_VOICEMEMO_UTC_MANIFEST=~/Notes/audio/voice_memo_utc_manifest.txt` (for one-time timezone incident files)
- `MEETINGCTL_NORMALIZE_FRONTMATTER=1` (optional: normalize meeting metadata after each ingest run)
- `MEETINGCTL_NORMALIZE_SCOPE=_Work` (optional: scope for normalization command)
- `MEETINGCTL_PROCESS_QUEUE_MAX_JOBS=3` (optional: jobs processed per drain pass)
- `MEETINGCTL_PROCESS_QUEUE_DRAIN_PASSES=6` (optional: max drain passes per trigger)
- `MEETINGCTL_PROCESS_QUEUE_FAILURE_MODE=dead_letter` (optional: do not block queue on bad job)
- `MEETINGCTL_PROCESS_QUEUE_DEAD_LETTER_FILE=~/.local/state/meetingctl/process_queue.deadletter.jsonl` (optional: failed job log)
- `MEETINGCTL_TRANSCRIPTION_TIMEOUT_SECONDS=1800` (optional: fail hung transcriptions after timeout)
- `MEETINGCTL_DOTENV_PATH=~/.config/meetingctl/env` (recommended env location outside repo)
- `MEETINGCTL_USE_1PASSWORD=auto` (default; use `op run` only when env includes `op://` refs)
- `MEETINGCTL_ENV_PROFILE=secure` (optional explicit profile)
- `MEETINGCTL_HAZEL_ENV_PROFILE=secure` (default for Hazel ingest in `secure_exec.sh`; set to `dev` only if you intentionally want non-secret local config)
- `MEETINGCTL_ANTHROPIC_API_KEY_OP_REF=op://Private/Anthropic/api_key` (recommended 1Password ref)
- `MEETINGCTL_SUMMARY_USE_SYSTEM_TRUST=1` (recommended: use macOS trust roots via `truststore` for Anthropic TLS)
- `MEETINGCTL_SUMMARY_REQUEST_RETRIES=2` (optional: retries for transient 429/529/connection errors)
- `MEETINGCTL_SUMMARY_RETRY_BASE_SECONDS=2` (optional: exponential backoff base delay)
- `MEETINGCTL_AUDIO_DONE_MODE=sidecar` (default: create `<audio>.done.json`; use `none` to disable)

## Quick Validation

1. Manual script run with a known file:
   - `bash scripts/hazel_ingest_file.sh "/absolute/path/to/test.m4a"`
2. Check Hazel log:
   - `tail -n 100 ~/.local/state/meetingctl/hazel.log`
3. Confirm queue processing + artifacts:
   - `PYTHONPATH=src python3 -m meetingctl.cli process-queue --json`
4. Normalize frontmatter on work notes (location-based inference):
   - `PYTHONPATH=src python3 -m meetingctl.cli normalize-frontmatter --scope _Work --json`
5. Audit duplicate meeting notes after bulk runs:
   - `PYTHONPATH=src python3 -m meetingctl.cli audit-notes --json`

## Failed Jobs Monitoring + Reprocess

- List latest failed jobs from dead-letter:
  - `PYTHONPATH=src python3 -m meetingctl.cli failed-jobs --limit 20 --json`
- Requeue all failed jobs:
  - `PYTHONPATH=src python3 -m meetingctl.cli failed-jobs-requeue --json`
- Requeue specific meeting IDs:
  - `PYTHONPATH=src python3 -m meetingctl.cli failed-jobs-requeue --meeting-id m-abc123 --meeting-id m-def456 --json`
