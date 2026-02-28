#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/load_dotenv.sh"

CONFIG_DIR="$HOME/.config/meetingctl"
BASE_ENV="${MEETINGCTL_BASE_ENV_PATH:-$CONFIG_DIR/env}"
DEV_ENV="${MEETINGCTL_DEV_ENV_PATH:-$CONFIG_DIR/env.dev}"
SECURE_ENV="${MEETINGCTL_SECURE_ENV_PATH:-$CONFIG_DIR/env.secure}"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR" || true

if [[ ! -f "$BASE_ENV" ]]; then
  if [[ -f "$ROOT_DIR/.env" ]]; then
    cp "$ROOT_DIR/.env" "$BASE_ENV"
  elif [[ -f "$ROOT_DIR/.env.example" ]]; then
    cp "$ROOT_DIR/.env.example" "$BASE_ENV"
  else
    echo "No base env source found (.env or .env.example)."
    exit 1
  fi
fi

cp "$BASE_ENV" "$DEV_ENV"
cp "$BASE_ENV" "$SECURE_ENV"

# Ensure profile toggles are explicit.
if rg -q '^MEETINGCTL_USE_1PASSWORD=' "$DEV_ENV"; then
  sed -i '' 's/^MEETINGCTL_USE_1PASSWORD=.*/MEETINGCTL_USE_1PASSWORD=0/' "$DEV_ENV"
else
  printf '\nMEETINGCTL_USE_1PASSWORD=0\n' >> "$DEV_ENV"
fi

if rg -q '^MEETINGCTL_USE_1PASSWORD=' "$SECURE_ENV"; then
  sed -i '' 's/^MEETINGCTL_USE_1PASSWORD=.*/MEETINGCTL_USE_1PASSWORD=auto/' "$SECURE_ENV"
else
  printf '\nMEETINGCTL_USE_1PASSWORD=auto\n' >> "$SECURE_ENV"
fi

# Secure profile should avoid plaintext Anthropic key by default.
if rg -q '^ANTHROPIC_API_KEY=' "$SECURE_ENV"; then
  sed -i '' 's/^ANTHROPIC_API_KEY=.*/# ANTHROPIC_API_KEY=/' "$SECURE_ENV"
fi
if ! rg -q '^MEETINGCTL_ANTHROPIC_API_KEY_OP_REF=' "$SECURE_ENV"; then
  printf 'MEETINGCTL_ANTHROPIC_API_KEY_OP_REF=op://Private/Anthropic/api_key\n' >> "$SECURE_ENV"
fi

chmod 600 "$BASE_ENV" "$DEV_ENV" "$SECURE_ENV" || true

echo "Created/updated:"
echo "  base:   $BASE_ENV"
echo "  dev:    $DEV_ENV"
echo "  secure: $SECURE_ENV"
echo
echo "Usage:"
echo "  Manual secure CLI: MEETINGCTL_ENV_PROFILE=secure bash \"$ROOT_DIR/scripts/meetingctl_cli.sh\" doctor --json"
echo "  Manual dev CLI:    MEETINGCTL_ENV_PROFILE=dev bash \"$ROOT_DIR/scripts/meetingctl_cli.sh\" doctor --json"
echo "  Hazel defaults to dev profile via scripts/secure_exec.sh."
