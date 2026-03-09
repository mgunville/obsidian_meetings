# Local Diarization Sidecar (Pyannote in Container)

This project now includes a containerized diarization path that is isolated from the host Python environment.

## Why this exists

- Host runtime dependency conflicts (torch/pyannote/whisperx) are common.
- The sidecar pins diarization dependencies independently.
- Main `meetingctl` workflow remains stable.

## Files

- `docker/diarization/Dockerfile`
- `docker/diarization/requirements.txt`
- `docker/diarization/diarize.py`
- `docker-compose.diarization.yml`
- `scripts/diarize_sidecar.sh`
- `shared_data/diarization/`

## Prerequisites

- Docker Desktop running locally.
- Hugging Face token with access to pyannote diarization models.
- No Hugging Face MCP server is required or used by this runtime.
- Access must include dependent gated segmentation repos used by diarization pipelines:
  - `pyannote/segmentation-3.0` (used by `speaker-diarization-3.1`)
  - `pyannote/segmentation` (used by legacy `speaker-diarization`)
- Token available in your env (or 1Password ref), one of:
  - `PYANNOTE_AUTH_TOKEN`
  - `HF_TOKEN`
  - `HUGGINGFACE_TOKEN`
  - or `MEETINGCTL_HF_TOKEN_FILE=~/.config/meetingctl/hf_token` (token file on host; wrapper exports it as env)

Destination-machine setup:
- Accept gated model access once in a browser for the HF account tied to your token:
  - [https://huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
  - [https://huggingface.co/pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization)
  - [https://huggingface.co/pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
  - [https://huggingface.co/pyannote/segmentation](https://huggingface.co/pyannote/segmentation)
- If you are not using `op://...` refs, create a local token file:
  - `mkdir -p ~/.config/meetingctl`
  - `chmod 700 ~/.config/meetingctl`
  - `printf '%s\n' '<hf-token>' > ~/.config/meetingctl/hf_token`
  - `chmod 600 ~/.config/meetingctl/hf_token`
  - set `MEETINGCTL_HF_TOKEN_FILE=~/.config/meetingctl/hf_token`
- If you are using `op://...` refs, install 1Password CLI and confirm `op whoami` succeeds before sidecar runs.

1Password note:
- If your configured env file contains `op://...`, `scripts/diarize_sidecar.sh` runs through `scripts/secure_exec.sh` so the token resolves at runtime.
- For consistent pyannote diarization in automations, run with `MEETINGCTL_ENV_PROFILE=secure` (or `MEETINGCTL_HAZEL_ENV_PROFILE=secure` for Hazel).

## Build

```bash
cd /Users/michael.gunville/Dev/obsidian_meetings
docker compose -f docker-compose.diarization.yml build diarizer
```

Validate the destination machine before the first real run:

```bash
cd /Users/michael.gunville/Dev/obsidian_meetings
docker info
docker compose -f docker-compose.diarization.yml config
bash scripts/diarization_model_sync.sh --json
```

## Run (single file)

```bash
cd /Users/michael.gunville/Dev/obsidian_meetings
bash scripts/diarize_sidecar.sh ~/Notes/audio/20260303-0959_Audio.wav --meeting-id m-4d393affc5
```

Optional controls:

- `--job-id <id>`
- `--min-speakers <N>`
- `--max-speakers <N>`
- `--transcript-json </path/to/transcript.json>` (reuse existing segments; skip sidecar ASR)
- `--allow-transcript-without-diarization` (keeps transcript if diarization fails)
- `--no-diarization` (transcription-only sidecar run)
- `--require-pyannote` (disable embedding fallback; fail if pyannote is unavailable)

Diarization behavior:
- Tries pyannote model IDs in order from `WHISPERX_DIARIZATION_MODELS`.
- If a fully cached local snapshot exists (contains `config.yaml`), sidecar prefers that local snapshot first.
- If pyannote access fails, optional fallback `WHISPERX_DIARIZATION_EMBEDDING_FALLBACK=1` uses local segment embeddings + agglomerative clustering to label `SPEAKER_00/01/...`.
- Fallback can auto-select speaker count (`WHISPERX_DIARIZATION_AUTO_CLUSTER=1`) with guardrails for tiny/noisy clusters.
- Transcript `.txt` is emitted as speaker turns, splitting on speaker change, on gaps larger than `WHISPERX_TURN_MAX_GAP_SECONDS` (default `1.5`), and on long spans above `WHISPERX_TURN_MAX_DURATION_SECONDS` (default `90`).

## Outputs

Outputs are written under:

- `shared_data/diarization/jobs/<job_id>/`

Per run files:

- `transcript_diarized.txt`
- `transcript_diarized.srt`
- `transcript_diarized.json`
- `manifest.json`

Caches:

- `shared_data/diarization/cache/hf`
- `shared_data/diarization/cache/transformers`

Useful env knobs:
- `WHISPERX_DIARIZATION_MODELS=pyannote/speaker-diarization-3.1,pyannote/speaker-diarization`
- `WHISPERX_OFFLINE_MODE=1` (default; cached-model-only)
- `WHISPERX_DOWNLOAD_ROOT=/shared/diarization/cache/hf`
- `MEETINGCTL_HF_TOKEN_FILE=~/.config/meetingctl/hf_token` (host-side token file for refresh/bootstrap runs)
- `MEETINGCTL_DIARIZATION_INSECURE_SSL=1` (last resort when managed TLS interception breaks HF cert validation)
- `HF_HUB_DISABLE_XET=1` (recommended on managed networks to avoid xethub TLS issues)
- `WHISPERX_DIARIZATION_EMBEDDING_FALLBACK=1`
- `WHISPERX_DIARIZATION_REQUIRE_PYANNOTE=0` (set `1` for strict production mode)
- `WHISPERX_DIARIZATION_SEGMENT_CLUSTER_DISTANCE=0.08` (used when auto clustering is disabled or inconclusive)
- `WHISPERX_DIARIZATION_AUTO_CLUSTER=1`
- `WHISPERX_DIARIZATION_AUTO_MIN_SPEAKERS=2`
- `WHISPERX_DIARIZATION_AUTO_MAX_SPEAKERS=6`
- `WHISPERX_DIARIZATION_AUTO_MIN_CLUSTER_FRACTION=0.06`
- `WHISPERX_DIARIZATION_AUTO_MIN_CLUSTER_WINDOWS=3`
- `WHISPERX_DIARIZATION_AUTO_MIN_SILHOUETTE=0.12`
- `WHISPERX_DIARIZATION_AUTO_SCORE_SAMPLE_MAX=1000`
- `WHISPERX_DIARIZATION_LABEL_SMOOTH_SPAN=5`
- `WHISPERX_DIARIZATION_MIN_SEGMENTS_PER_SPEAKER=2` (collapse one-off outlier speakers)
- `WHISPERX_DIARIZATION_MIN_SEGMENT_SPEAKER_FRACTION=0.03`
- `WHISPERX_TURN_MAX_GAP_SECONDS=1.5`
- `WHISPERX_TURN_MAX_DURATION_SECONDS=90`

## Deploy/Compose details

This is intentionally a run-on-demand sidecar (not always-on service).

- Build image:
  - `docker compose -f docker-compose.diarization.yml build diarizer`
- Execute one job:
  - `docker compose -f docker-compose.diarization.yml run --rm diarizer --input /host_audio/<file> ...`
- Verify final runtime config:
  - `docker compose -f docker-compose.diarization.yml config`

`docker-compose.diarization.yml` mounts:

- repo root at `/workspace`
- `./shared_data` at `/shared`
- host audio directory at `/host_audio` (read-only; auto-set by wrapper per input file)
- optional transcript-json directory at `/host_transcript` (read-only; auto-set when `--transcript-json` is provided)

## Offline-first + Monthly Refresh

- Default behavior is offline-first (`WHISPERX_OFFLINE_MODE=1`), reusing local cache under `shared_data/diarization/cache/*`.
- If your token is unavailable on this machine, copy the pyannote cache from another machine that already has access:
  - `shared_data/diarization/cache/hf/models--pyannote--*`
  - `shared_data/diarization/cache/hf/blobs/*` (required by snapshot symlinks)
  - Sidecar will use local snapshots when `config.yaml` is present.
- To check remote model revisions and optionally refresh cache on a monthly cadence:
  - check-only: `bash scripts/diarization_model_sync.sh --json`
  - refresh: `bash scripts/diarization_model_sync.sh --refresh --json`
- `.env`-based reminder (simple model; no separate state DB):
  - `MEETINGCTL_DIARIZATION_MODEL_LAST_CHECK_AT=<ISO8601 UTC>`
  - `MEETINGCTL_DIARIZATION_MODEL_LAUNCH_COUNT_SINCE_CHECK=<int>`
  - `MEETINGCTL_DIARIZATION_MODEL_CHECK_INTERVAL_DAYS=30`
  - `MEETINGCTL_DIARIZATION_MODEL_CHECK_INTERVAL_LAUNCHES=180`
  - `MEETINGCTL_DIARIZATION_MODEL_CHECK_REMINDER=1`
  - optional: `MEETINGCTL_DIARIZATION_MODEL_DOTENV_PATH=/path/to/.env` (default: repo `.env`)
  - `scripts/run_ingest_once.sh` increments launch count and prints a reminder when either threshold is due.
  - `scripts/diarization_model_sync.sh` updates `MEETINGCTL_DIARIZATION_MODEL_LAST_CHECK_AT` and resets launch count to `0` after a successful check/refresh.

## Current integration boundary

- Sidecar is integrated as a transcription backend (`MEETINGCTL_TRANSCRIPTION_BACKEND=sidecar`).
- Runtime behavior:
  - diarization sidecar runs first
  - if sidecar ASR/diarization fails, pipeline can fall back to whisper (`MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER=1`)
  - after whisper fallback, runner performs a best-effort second sidecar pass using `--transcript-json` to recover speaker labels from the fallback transcript segments
  - on diarization success, active transcript is updated and baseline transcript can be retained as `.basic.*` (`MEETINGCTL_DIARIZATION_KEEP_BASELINE=1`)
- Historical catch-up + comparison workflow:
  - `bash scripts/run_diarization_backfill.sh` (recommended)
  - `./.venv/bin/python scripts/diarization_catchup.py --json`
  - `bash scripts/secure_exec.sh ./.venv/bin/python scripts/diarization_minutes_refresh.py --max-items 10 --json`
  - `docs/DIARIZATION_CATCHUP_AGENT.md`

## Backfill Design Notes

- For historical updates, prefer `--transcript-json` inputs from existing meeting artifacts (`m-<id>.json`).
- This transcript-json-first path avoids sidecar ASR model bootstrap fragility and isolates diarization quality improvements.
- `scripts/diarization_catchup.py` now supports:
  - `--prefer-existing-transcript-json` (default)
  - `--require-existing-transcript-json` (skip files that lack baseline segment JSON)
  - `--require-pyannote` (disable embedding fallback for strict quality gates)
