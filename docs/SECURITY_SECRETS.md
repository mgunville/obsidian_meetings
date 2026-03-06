# Security: Secrets and Runtime Hardening

## Goals

- Keep API keys out of repo/workspace/cloud-synced project paths.
- Prefer 1Password-backed secret resolution.
- Minimize persistence and blast radius for failed/hung jobs.

## Recommended Env File Location

- Use `~/.config/meetingctl/env` for runtime config.
- Override with `MEETINGCTL_DOTENV_PATH=/absolute/path/to/env` when needed.
- Legacy repo `.env` is supported as fallback, but not recommended for secrets.

Profiles:
- `~/.config/meetingctl/env.dev` for low-friction automation runs
- `~/.config/meetingctl/env.secure` for higher-assurance manual runs

Set permissions:

```bash
mkdir -p ~/.config/meetingctl
chmod 700 ~/.config/meetingctl
touch ~/.config/meetingctl/env
chmod 600 ~/.config/meetingctl/env
```

## 1Password Pattern

Use secret references rather than plaintext keys:

```bash
VAULT_PATH=~/Notes/notes-vault
RECORDINGS_PATH=~/Notes/audio
MEETINGCTL_ANTHROPIC_API_KEY_OP_REF=op://Private/Anthropic/api_key
HUGGINGFACE_TOKEN=op://Private/HuggingFace/token
MEETINGCTL_SUMMARY_MODEL=claude-3-5-sonnet-latest
```

Runtime behavior:
- `scripts/secure_exec.sh` can use `op run --env-file <env>`.
- `MEETINGCTL_USE_1PASSWORD` controls wrapper behavior:
  - `auto` (default): use `op run` only when env file contains `op://` refs
  - `1`: always use `op run`
  - `0`: skip `op run`
- Optional auth-friction reduction for local development:
  - `MEETINGCTL_OP_CACHE_TTL_SECONDS=<seconds>` caches resolved env values locally (for example `21600` for 6h)
  - `MEETINGCTL_OP_CACHE_DIR=~/.local/state/meetingctl/op-cache` controls cache location
  - `0` or unset disables caching
- `meetingctl` resolves `MEETINGCTL_ANTHROPIC_API_KEY_OP_REF` via `op read` at summary time.
- Diarization sidecar can receive `HUGGINGFACE_TOKEN` via `op run` env expansion.
- Alternative for lower-friction local development: set `MEETINGCTL_HF_TOKEN_FILE=~/.config/meetingctl/hf_token`
  with `chmod 600 ~/.config/meetingctl/hf_token`; wrapper exports it for sidecar/model-sync runs.
- `MEETINGCTL_ENV_PROFILE` controls default env file selection:
  - `dev` -> `~/.config/meetingctl/env.dev`
  - `secure` -> `~/.config/meetingctl/env.secure` (fallback `~/.config/meetingctl/env`)

Cache security note:
- Cache files are plaintext env values stored with `0600` permissions in a user-only directory.
- Use short TTLs on shared/high-risk machines and set `MEETINGCTL_OP_CACHE_TTL_SECONDS=0` when higher assurance is required.

Initialize profile files:

```bash
bash scripts/setup_env_profiles.sh
```

## Secure Command Entry Points

- Preferred CLI wrapper:

```bash
bash scripts/meetingctl_cli.sh doctor --json
```

- Explicit profile selection:

```bash
MEETINGCTL_ENV_PROFILE=secure bash scripts/meetingctl_cli.sh doctor --json
MEETINGCTL_ENV_PROFILE=dev bash scripts/meetingctl_cli.sh doctor --json
```

- Generic secure wrapper:

```bash
bash scripts/secure_exec.sh <command> [args...]
```

- Diarization sidecar wrapper (also uses `secure_exec.sh`):

```bash
bash scripts/diarize_sidecar.sh ~/Notes/audio/<file>.wav --meeting-id <meeting_id>
```

## Hazel / Automation

Use secure wrapper in Hazel shell action:

```bash
REPO_ROOT="${MEETINGCTL_REPO:-$HOME/Dev/obsidian_meetings}"
bash "$REPO_ROOT/scripts/secure_exec.sh" \
  bash "$REPO_ROOT/scripts/hazel_ingest_file.sh" "$1" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
```

`secure_exec.sh` auto-selects `secure` profile for Hazel ingest scripts unless overridden.
Use `MEETINGCTL_HAZEL_ENV_PROFILE=dev` only for explicit non-secret/local testing.

## Failure Isolation and Monitoring

- Queue failure mode:
  - `MEETINGCTL_PROCESS_QUEUE_FAILURE_MODE=dead_letter`
  - `MEETINGCTL_PROCESS_QUEUE_DEAD_LETTER_FILE=~/.local/state/meetingctl/process_queue.deadletter.jsonl`
- Hung transcription guard:
  - `MEETINGCTL_TRANSCRIPTION_TIMEOUT_SECONDS=1800`

Inspect and requeue failures:

```bash
bash scripts/meetingctl_cli.sh failed-jobs --limit 20 --json
bash scripts/meetingctl_cli.sh failed-jobs-requeue --json
```

## Threat Model Note

These controls reduce accidental disclosure and persistence risk, but cannot fully protect against a fully compromised host or privileged local administrator.
