# Hazel Setup

Use Hazel as the first-line file trigger for completed recordings.

## Rule Target

- Folder: `~/Notes/audio`
- Rule Name: `MeetingCtl - Ingest WAV`

## Conditions

- `Extension` `is` `wav`
- `Date Last Modified` `is not in the last` `1` `minute`
- `Name` `does not start with` `.`

Notes:
- Only trigger on `.wav` to avoid duplicate handling of `.m4a`.
- The 1-minute guard reduces partial-write races from Audio Hijack.

## Action

- `Run shell script`:

```bash
bash "/Users/michael.gunville/Library/CloudStorage/OneDrive-AHEADInc(Production)/Documents/Dev/obsidian_meetings/scripts/run_ingest_once.sh" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
```

## Runtime Behavior

- Script loads `.env` and `.venv`.
- Runs one ingest pass with calendar matching.
- Processes queue after ingest.
- Uses lock directory `~/.local/state/meetingctl/automation_ingest.lock` to skip duplicate concurrent triggers.

## Optional Tuning (`.env`)

- `MEETINGCTL_MATCH_WINDOW_MINUTES=30`
- `MEETINGCTL_INGEST_MIN_AGE_SECONDS=15`
- `MEETINGCTL_BACKFILL_EXTENSIONS=wav`
- `MEETINGCTL_AUTOMATION_STATE_DIR=~/.local/state/meetingctl`

## Quick Validation

1. Confirm command works manually:
   - `bash scripts/run_ingest_once.sh`
2. Check logs:
   - `tail -n 100 ~/.local/state/meetingctl/hazel.log`
3. Confirm queue is draining:
   - `PYTHONPATH=src python -m meetingctl.cli process-queue --json`
