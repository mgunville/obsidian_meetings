# Operations Runbook

This runbook captures the commands used in day-to-day operation and bulk maintenance.

## 1) Standard Environment

Run from repo root:

```bash
REPO_ROOT="${MEETINGCTL_REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$REPO_ROOT"
```

Recommended runtime for all commands:

```bash
bash scripts/meetingctl_cli.sh --help
```

Dependency checks:

```bash
which ffmpeg
which whisper
```

## 2) Primary Batch Command (Manifest Driven)

Use a curated list of known-good `.m4a` files:

```bash
RECORDINGS_PATH=~/Notes/audio bash scripts/meetingctl_cli.sh backfill \
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
  - `VAULT_PATH/<MEETINGCTL_ARTIFACTS_ROOT>/<meeting_id>/`
  - Files: `<meeting_id>.txt`, `<meeting_id>.srt`, `<meeting_id>.json`

The default behavior is enabled with:

```bash
MEETINGCTL_TEXT_ARTIFACTS_IN_VAULT=1
MEETINGCTL_ARTIFACTS_ROOT=Meetings/_artifacts
```

Set `MEETINGCTL_TEXT_ARTIFACTS_IN_VAULT=0` to keep text artifacts in `RECORDINGS_PATH`.

## 5) Validation Commands

Duplicate/identity check across meeting notes:

```bash
bash scripts/meetingctl_cli.sh audit-notes --json
```

Dry-run calendar matching and export unmatched list:

```bash
RECORDINGS_PATH=~/Notes/audio bash scripts/meetingctl_cli.sh backfill \
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
./.venv/bin/python scripts/audit_vault_tags.py "${VAULT_PATH:?set VAULT_PATH in .env}" --max-examples 30
./.venv/bin/python scripts/fix_vault_tags.py "${VAULT_PATH:?set VAULT_PATH in .env}" --drop-year-tags --write --report /tmp/vault_tags_drop_year_write.json
```

## 7) Replacing Transcript After Diarization (Future)

Note: this section reflects current behavior where transcript body can be managed inline.
For the planned links-only transcript model and vault metadata normalization rules, use:
- `docs/VAULT_METADATA_NORMALIZATION_RUNBOOK.md`

When diarized output is ready for a meeting:

1. Replace the text artifact file:
   - `.../<MEETINGCTL_ARTIFACTS_ROOT>/<meeting_id>/<meeting_id>.txt`
2. Re-run processing for that meeting ID.
3. The managed note sections are overwritten from the new transcript:
   - `TRANSCRIPT`
   - minutes/decisions/action items

This is repeatable and intended for transcript upgrades.

## 8) Common Failure Signals

- `No such file or directory` during manifest run:
  - stale manifest entry; run manifest hygiene.
- `invalid x-api-key` / `401`:
  - bad key value or unresolved 1Password ref in configured env file.
- `model ... not found` / `404`:
  - wrong `MEETINGCTL_SUMMARY_MODEL`.
- `moov atom not found`:
  - corrupted/incomplete audio file; exclude from manifest.

## 9) Automation Setup (Hazel + Keyboard Maestro)

### Hazel

Use `docs/HAZEL_SETUP.md` as the source of truth. Both monitored folders should run:

```bash
REPO_ROOT="${MEETINGCTL_REPO:-$HOME/Documents/Dev/obsidian_meetings}"
bash "$REPO_ROOT/scripts/secure_exec.sh" \
  bash "$REPO_ROOT/scripts/hazel_ingest_file.sh" "$1" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
```

Recommended post-process metadata hygiene step:

```bash
REPO_ROOT="${MEETINGCTL_REPO:-$HOME/Documents/Dev/obsidian_meetings}"
cd "$REPO_ROOT"
bash scripts/meetingctl_cli.sh normalize-frontmatter --scope _Work --json
```

### Keyboard Maestro

1. Import macro bundle:
   - `config/km/Meeting-Automation-Macros.kmmacros`
2. Ensure macro shell actions use repo-local runtime:
   - `REPO_ROOT="${MEETINGCTL_REPO:-$HOME/Documents/Dev/obsidian_meetings}" && cd "$REPO_ROOT"`
   - `bash scripts/meetingctl_cli.sh ...`
3. Validate macro command path from terminal first:

```bash
REPO_ROOT="${MEETINGCTL_REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$REPO_ROOT"
bash scripts/meetingctl_cli.sh status --json
```

4. UI/macros reference:
   - `docs/UI-QUICKSTART.md`
   - `docs/HOTKEYS.md`
