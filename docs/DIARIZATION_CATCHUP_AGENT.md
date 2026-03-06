# Diarization Catch-up Agent Runbook (Cross-Machine)

Use this runbook on any machine that has:
- this repo checked out
- Docker Desktop
- access to your local Notes vault/audio
- 1Password CLI configured (if env uses `op://` refs)

## Goal

1. Generate diarized transcripts for historical audio.
2. Keep baseline transcript and diarized transcript side-by-side.
3. Compare minutes quality before bulk applying diarized minutes.

## 0) Preflight

```bash
cd /Users/michael.gunville/Dev/obsidian_meetings
bash scripts/meetingctl_cli.sh doctor --json
```

Ensure Docker Desktop is running:

```bash
docker info >/dev/null
```

## 1) Build sidecar image

```bash
docker compose -f docker-compose.diarization.yml build diarizer
```

## 2) Smoke test one known file

```bash
bash scripts/diarize_sidecar.sh ~/Notes/audio/20260303-0959_Audio.wav --meeting-id m-4d393affc5
```

Expected output:
- JSON manifest in terminal
- output folder created under `shared_data/diarization/jobs/<job_id>/`

## 3) Historical catch-up (safe mode, keep both)

This writes `m-<id>.diarized.txt/.srt/.json` under meeting artifacts and keeps existing `m-<id>.txt` untouched.

Recommended wrapper (transcript-json-first, strict pyannote, replace active canonical transcript with diarized):

```bash
bash scripts/run_diarization_backfill.sh
```

Equivalent direct command:

```bash
./.venv/bin/python scripts/diarization_catchup.py \
  --prefer-existing-transcript-json \
  --require-existing-transcript-json \
  --require-pyannote \
  --replace-active \
  --json
```

Optional bounded run:

```bash
bash scripts/run_diarization_backfill.sh --max-files 25
```

Optional explicit manifest run:

```bash
./.venv/bin/python scripts/diarization_catchup.py --file-list ~/Notes/audio/diarize_manifest.txt --json
```

## 4) Minutes quality comparison

Generate side-by-side baseline vs diarized summary outputs without changing notes:

```bash
bash scripts/secure_exec.sh ./.venv/bin/python scripts/diarization_minutes_refresh.py --max-items 10 --json
```

Reports:
- `shared_data/diarization/manifests/minutes_compare_<timestamp>.json`
- `shared_data/diarization/manifests/minutes_compare_<timestamp>.md`

## 5) Apply diarized minutes after review

Apply diarized minutes/decisions/action items to notes for compared items:

```bash
bash scripts/secure_exec.sh ./.venv/bin/python scripts/diarization_minutes_refresh.py --max-items 10 --apply-diarized --json
```

Or target specific meetings:

```bash
bash scripts/secure_exec.sh ./.venv/bin/python scripts/diarization_minutes_refresh.py \
  --meeting-id m-4d393affc5 \
  --meeting-id m-2969ffd682 \
  --apply-diarized --json
```

## 6) Going forward defaults (diarized-first)

Set in your active env profile (`~/.config/meetingctl/env.dev` and/or `.secure`):

```bash
MEETINGCTL_TRANSCRIPTION_BACKEND=sidecar
MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER=1
MEETINGCTL_DIARIZATION_KEEP_BASELINE=1
MEETINGCTL_DIARIZATION_REQUIRE_SPEAKER_LABELS=1
# Optional tuning
# MEETINGCTL_DIARIZATION_MIN_SPEAKERS=2
# MEETINGCTL_DIARIZATION_MAX_SPEAKERS=8
```

Behavior:
- tries sidecar diarization first
- if diarization fails, falls back to whisper baseline transcript
- when diarization succeeds, also writes `.basic.*` once for comparison

## 7) Known runtime notes

- Sidecar ASR model bootstrap can fail on managed networks due TLS interception.
- For historical backfill, transcript-json-first mode avoids sidecar ASR and runs pyannote directly against existing segment JSON.
