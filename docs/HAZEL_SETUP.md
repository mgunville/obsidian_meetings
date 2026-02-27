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
bash "$REPO_ROOT/scripts/hazel_ingest_file.sh" "$1" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
```

## Runtime Behavior

- `hazel_ingest_file.sh` accepts the triggered file path from Hazel.
- It stages files into `RECORDINGS_PATH` (from `.env`) if they originate outside that folder.
- It accepts `.wav` and `.m4a`.
- It then runs `scripts/run_ingest_once.sh`:
  - loads `.env` and `.venv`
  - runs `ingest-watch --once --match-calendar --json`
  - runs `process-queue --json`
  - optional (`MEETINGCTL_NORMALIZE_FRONTMATTER=1`): runs `normalize-frontmatter` for new/moved notes
- Locking via `~/.local/state/meetingctl/automation_ingest.lock` prevents duplicate concurrent runs.

## Required `.env`

- `RECORDINGS_PATH` should point at your canonical ingest folder (for example `~/Notes/audio`).

## Optional Tuning (`.env`)

- `MEETINGCTL_MATCH_WINDOW_MINUTES=30`
- `MEETINGCTL_INGEST_MIN_AGE_SECONDS=15`
- `MEETINGCTL_BACKFILL_EXTENSIONS=wav,m4a`
- `MEETINGCTL_INGEST_EXTENSIONS=wav,m4a`
- `MEETINGCTL_AUTOMATION_STATE_DIR=~/.local/state/meetingctl`
- `MEETINGCTL_VOICEMEMO_FILENAME_TIMEZONE=America/Chicago`
- `MEETINGCTL_VOICEMEMO_UTC_MANIFEST=~/Notes/audio/voice_memo_utc_manifest.txt` (for one-time timezone incident files)
- `MEETINGCTL_NORMALIZE_FRONTMATTER=1` (optional: normalize meeting metadata after each ingest run)
- `MEETINGCTL_NORMALIZE_SCOPE=_Work` (optional: scope for normalization command)

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
