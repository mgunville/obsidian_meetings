# Operations Runbook

This runbook captures the commands used in day-to-day operation and bulk maintenance.

## 1) Standard Environment

Run from repo root:

```bash
cd /Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings
set -a; source .env; set +a
```

Recommended runtime for all commands:

```bash
PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli --help
```

Dependency checks:

```bash
which ffmpeg
which whisper
```

## 2) Primary Batch Command (Manifest Driven)

Use a curated list of known-good `.m4a` files:

```bash
RECORDINGS_PATH=~/Notes/audio PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli backfill \
  --extensions m4a \
  --file-list ~/Notes/audio/valid_m4a_manifest.txt \
  --match-calendar \
  --process-now \
  --progress \
  --verbose \
  --json
```

## 3) Manifest Hygiene (Missing or Stale Paths)

If a manifest entry was moved/deleted, rebuild a clean manifest:

```bash
awk 'NF && system("[ -f \"" $0 "\" ]")==0' ~/Notes/audio/valid_m4a_manifest.txt > ~/Notes/audio/valid_m4a_manifest.clean.txt
mv ~/Notes/audio/valid_m4a_manifest.clean.txt ~/Notes/audio/valid_m4a_manifest.txt
```

Optional preflight decode test for all manifest files:

```bash
while IFS= read -r f; do ffprobe -v error "$f" >/dev/null || echo "BAD: $f"; done < ~/Notes/audio/valid_m4a_manifest.txt
```

## 4) Current Artifact Policy

- Keep audio files (`.m4a`, optional `.mp3`) in `~/Notes/audio`.
- Store text artifacts in vault under:
  - `VAULT_PATH/<DEFAULT_MEETINGS_FOLDER>/_artifacts/<meeting_id>/`
  - Files: `<meeting_id>.txt`, `<meeting_id>.srt`, `<meeting_id>.json`

The default behavior is enabled with:

```bash
MEETINGCTL_TEXT_ARTIFACTS_IN_VAULT=1
```

Set `MEETINGCTL_TEXT_ARTIFACTS_IN_VAULT=0` to keep text artifacts in `RECORDINGS_PATH`.

## 5) Validation Commands

Duplicate/identity check across meeting notes:

```bash
PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli audit-notes --json
```

Dry-run calendar matching and export unmatched list:

```bash
RECORDINGS_PATH=~/Notes/audio PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli backfill \
  --extensions m4a \
  --file-list ~/Notes/audio/valid_m4a_manifest.txt \
  --match-calendar \
  --dry-run \
  --export-unmatched-manifest ~/Notes/audio/unmatched_m4a_manifest.txt \
  --json
```

## 6) Maintenance Tasks

Delete `.mp3` files that have the same stem as an existing `.m4a` (safe cleanup):

```bash
find ~/Notes/audio -type f -name '*.mp3' | while read -r mp3; do
  stem="${mp3%.mp3}"
  [ -f "${stem}.m4a" ] && rm -f "$mp3"
done
```

Run tags normalization helpers (from repo):

```bash
./.venv/bin/python scripts/audit_vault_tags.py /Users/mike/Notes/notes-vault --max-examples 30
./.venv/bin/python scripts/fix_vault_tags.py /Users/mike/Notes/notes-vault --drop-year-tags --write --report /tmp/vault_tags_drop_year_write.json
```

## 7) Replacing Transcript After Diarization (Future)

When diarized output is ready for a meeting:

1. Replace the text artifact file:
   - `.../_artifacts/<meeting_id>/<meeting_id>.txt`
2. Re-run processing for that meeting ID.
3. The managed note sections are overwritten from the new transcript:
   - `TRANSCRIPT`
   - minutes/decisions/action items

This is repeatable and intended for transcript upgrades.

## 8) Common Failure Signals

- `No such file or directory` during manifest run:
  - stale manifest entry; run manifest hygiene.
- `invalid x-api-key` / `401`:
  - bad API key in `.env`.
- `model ... not found` / `404`:
  - wrong `MEETINGCTL_SUMMARY_MODEL`.
- `moov atom not found`:
  - corrupted/incomplete audio file; exclude from manifest.

## 9) Automation Setup (Hazel + Keyboard Maestro)

### Hazel

Use `docs/HAZEL_SETUP.md` as the source of truth. Both monitored folders should run:

```bash
bash "/Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings/scripts/hazel_ingest_file.sh" "$1" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
```

### Keyboard Maestro

1. Import macro bundle:
   - `config/km/Meeting-Automation-Macros.kmmacros`
2. Ensure macro shell actions use repo-local runtime:
   - `cd /Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings`
   - `set -a; source .env; set +a`
   - `PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli ...`
3. Validate macro command path from terminal first:

```bash
cd /Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings
set -a; source .env; set +a
PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli status --json
```

4. UI/macros reference:
   - `docs/UI-QUICKSTART.md`
   - `docs/HOTKEYS.md`
