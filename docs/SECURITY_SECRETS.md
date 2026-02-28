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
MEETINGCTL_SUMMARY_MODEL=claude-3-5-sonnet-latest
```

Runtime behavior:
- `scripts/secure_exec.sh` can use `op run --env-file <env>`.
- `MEETINGCTL_USE_1PASSWORD` controls wrapper behavior:
  - `auto` (default): use `op run` only when env file contains `op://` refs
  - `1`: always use `op run`
  - `0`: skip `op run`
- `meetingctl` resolves `MEETINGCTL_ANTHROPIC_API_KEY_OP_REF` via `op read` at summary time.
- `MEETINGCTL_ENV_PROFILE` controls default env file selection:
  - `dev` -> `~/.config/meetingctl/env.dev`
  - `secure` -> `~/.config/meetingctl/env.secure` (fallback `~/.config/meetingctl/env`)

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

## Hazel / Automation

Use secure wrapper in Hazel shell action:

```bash
REPO_ROOT="${MEETINGCTL_REPO:-$HOME/Documents/Dev/obsidian_meetings}"
bash "$REPO_ROOT/scripts/secure_exec.sh" \
  bash "$REPO_ROOT/scripts/hazel_ingest_file.sh" "$1" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
```

`secure_exec.sh` auto-selects `dev` profile for Hazel ingest scripts unless overridden.

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
