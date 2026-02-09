from __future__ import annotations

from pathlib import Path

import pytest

from meetingctl.config import ConfigError, load_config


def test_load_config_missing_required_keys_is_actionable() -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(env={})

    assert "VAULT_PATH" in str(excinfo.value)
    assert "RECORDINGS_PATH" in str(excinfo.value)


def test_load_config_normalizes_paths_to_absolute() -> None:
    cfg = load_config(
        env={
            "VAULT_PATH": "~/notes-vault",
            "RECORDINGS_PATH": "./recordings",
            "MEETINGCTL_STATE_FILE": "./state/current.json",
        }
    )

    assert cfg.vault_path.is_absolute()
    assert cfg.recordings_path.is_absolute()
    assert cfg.state_file.is_absolute()
    assert cfg.state_file.name == "current.json"


def test_load_config_uses_default_state_file() -> None:
    cfg = load_config(
        env={
            "VAULT_PATH": str(Path.cwd()),
            "RECORDINGS_PATH": str(Path.cwd() / "recordings"),
        }
    )
    assert cfg.state_file.name == "current.json"
