from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    vault_path: Path
    recordings_path: Path
    state_file: Path


REQUIRED_ENV_KEYS = ("VAULT_PATH", "RECORDINGS_PATH")
DEFAULT_STATE_FILE = "~/.local/state/meetingctl/current.json"


def _normalize_path(path_value: str) -> Path:
    return Path(os.path.expandvars(path_value)).expanduser().resolve()


def load_config(env: dict[str, str] | None = None) -> Config:
    effective_env = dict(os.environ if env is None else env)
    missing = [key for key in REQUIRED_ENV_KEYS if not effective_env.get(key)]
    if missing:
        raise ConfigError(
            "Missing required config keys: "
            + ", ".join(missing)
            + ". Set them in your environment or .env file."
        )

    return Config(
        vault_path=_normalize_path(effective_env["VAULT_PATH"]),
        recordings_path=_normalize_path(effective_env["RECORDINGS_PATH"]),
        state_file=_normalize_path(effective_env.get("MEETINGCTL_STATE_FILE", DEFAULT_STATE_FILE)),
    )
